import json
import datetime
from uuid import UUID
from typing import Annotated, Any, Optional
from pydantic import BaseModel, Field
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.tools import tool

from app.core.database import AsyncSessionLocal
from app.crud.link import get_link_analytics, get_link_by_id, get_links_for_project
from app.crud.project import get_project_by_id
from app.core.config import settings

# LangSmith natively reads from os.environ, not our Pydantic settings.
if hasattr(settings, "LANGCHAIN_API_KEY") and settings.LANGCHAIN_API_KEY:
    import os
    os.environ["LANGCHAIN_TRACING_V2"] = "true" if settings.LANGCHAIN_TRACING_V2 else "false"
    os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGCHAIN_ENDPOINT
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    # Configurable parameters will hold the user_id


async def _get_link_analytics_impl(link_id: str, user_id: str) -> str:
    try:
        if not user_id:
            return json.dumps({"error": "Unauthorized: No user context provided."})
            
        link_uuid = UUID(link_id)
        user_uuid = UUID(user_id)
        
        async with AsyncSessionLocal() as db:
            link = await get_link_by_id(db, link_uuid)
            if not link:
                return json.dumps({"error": "Link not found."})
                
            if str(link.created_by) != str(user_uuid):
                return json.dumps({"error": "Unauthorized: You do not own this link."})
                
            data = await get_link_analytics(db, link_uuid)
            
            # Convert UUIDs and datetime objects to strings for JSON serialization
            serialized_data = json.loads(json.dumps(data, default=str))
            return json.dumps(serialized_data)
            
    except ValueError:
        return json.dumps({"error": "Invalid UUID format."})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
async def get_link_analytics_tool(link_id: str, config: RunnableConfig) -> str:
    """
    Fetches detailed click analytics and demographics for a specific link.
    Returns JSON string with total clicks, unique visitors, devices, browsers, OS, referers, and timeline.
    """
    user_id = config.get("configurable", {}).get("user_id")
    return await _get_link_analytics_impl(link_id, user_id)


async def _get_project_summary_impl(project_id: str, user_id: str) -> str:
    try:
        if not user_id:
            return json.dumps({"error": "Unauthorized: No user context provided."})
            
        proj_uuid = UUID(project_id)
        user_uuid = UUID(user_id)
        
        async with AsyncSessionLocal() as db:
            project = await get_project_by_id(db, proj_uuid)
            if not project:
                return json.dumps({"error": "Project not found."})
                
            if str(project.owner_id) != str(user_uuid):
                return json.dumps({"error": "Unauthorized: You do not own this project."})
                
            links, total = await get_links_for_project(db, proj_uuid, page=1, per_page=100)
            
            # Serialize link objects
            serialized_links = []
            for item in links:
                link_obj = item["link"]
                serialized_links.append({
                    "id": str(link_obj.id),
                    "short_code": link_obj.short_code,
                    "original_url": link_obj.original_url,
                    "title": link_obj.title,
                    "click_count": item["click_count"]
                })
                
            return json.dumps({"project_name": project.name, "total_links": total, "links": serialized_links})
            
    except ValueError:
        return json.dumps({"error": "Invalid UUID format."})
    except Exception as e:
        return json.dumps({"error": str(e)})

@tool
async def get_project_summary_tool(project_id: str, config: RunnableConfig) -> str:
    """
    Retrieves a list of all links with their total click counts within a specific project.
    Returns JSON string with project details and list of links.
    """
    user_id = config.get("configurable", {}).get("user_id")
    return await _get_project_summary_impl(project_id, user_id)


# Define tools
tools = [get_link_analytics_tool, get_project_summary_tool]

# Base LLM
api_key = settings.model_dump().get("GROQ_API_KEY", "")
llm = ChatGroq(model_name="llama-3.3-70b-versatile", groq_api_key=api_key) if api_key else None
llm_with_tools = llm.bind_tools(tools) if llm else None

# Node for LLM
async def agent_node(state: AgentState):
    if not llm_with_tools:
        # Fallback if no API key is provided
        return {"messages": [HumanMessage(content="AI Analyst is not configured (missing GROQ_API_KEY).")]}
    
    messages = state["messages"]
    response = await llm_with_tools.ainvoke(messages)
    return {"messages": [response]}

# Build Graph
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", ToolNode(tools))

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", tools_condition)
workflow.add_edge("tools", "agent")

ai_agent = workflow.compile()

async def generate_insight_for_link(link_id: str, user_id: str, user_prompt: str = None) -> str:
    """Convenience function to generate a one-off insight for a specific link."""
    if not llm:
        return "AI Analyst is not configured. Please add GROQ_API_KEY to environment variables."
        
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
    system_prompt = SystemMessage(content="""
    You are an expert Data Analyst and Growth Marketer. 
    You analyze traffic data and provide actionable, concise insights based on user needs.
    Keep your response to 2 short paragraphs max. Focus on peak hours, device anomalies, or strong referers.
    You are an expert Data and Traffic Analyst.
    You analyze link traffic data and provide actionable, concise, and easy-to-understand insights.
    Your analysis should be tailored to the general user, whether they are a developer, a content creator, or just sharing a link with friends.
    Keep your response to 2 short paragraphs max unless the user asks for more detail. Focus on peak activity times, geographic or device anomalies, or strong referring sources.
    Do not mention UUIDs in your response.
    
    Current System Time: {current_time}
    Use this time to understand relative temporal references (e.g. 'yesterday', 'last week').
    """)
    
    if user_prompt and user_prompt.strip():
        human_content = f"The user is asking a specific question about link ID {link_id}: '{user_prompt.strip()}'. Please use your tools to fetch the necessary analytics and answer their exact question."
    else:
        human_content = f"Please fetch the analytics for link ID {link_id} and provide a summary of its performance over time."
        
    human_prompt = HumanMessage(content=human_content)
    
    config = {"configurable": {"user_id": user_id}}
    
    result = await ai_agent.ainvoke(
        {"messages": [system_prompt, human_prompt]},
        config=config
    )
    
    # The last message is the AI's final response
    return result["messages"][-1].content


# ── Link Comparison ───────────────────────────────────────────────────────────

async def _build_comparison_context(
    link_ids: list[str],
    user_id: str,
    db,
) -> dict | str:
    """
    Fetch compact analytics for each link and build a structured comparison
    context dict. Returns an error string on auth/not-found failures.
    All DB calls are sequential (AsyncSession constraint).
    """
    from urllib.parse import urlparse
    from uuid import UUID as _UUID

    user_uuid = _UUID(user_id)
    links_data = []

    for lid_str in link_ids:
        link_uuid = _UUID(lid_str)
        link = await get_link_by_id(db, link_uuid)

        if not link:
            return f"Link not found: {lid_str}"
        if str(link.created_by) != str(user_uuid):
            return f"Unauthorized: You do not own link with short code /{link.short_code}"

        a = await get_link_analytics(db, link_uuid)

        total   = a.get("total_clicks", 0)
        human   = a.get("human_clicks", 0)
        bots    = a.get("bot_clicks", 0)
        unique  = a.get("unique_visitors", 0)
        week    = a.get("clicks_this_week", 0)
        month   = a.get("clicks_this_month", 0)
        today   = a.get("clicks_today", 0)

        bot_pct       = round(bots / total * 100, 1) if total > 0 else 0.0
        unique_ratio  = round(unique / human, 2) if human > 0 else 0.0

        # 30-day trend: compare second half vs first half of timeline
        timeline = a.get("clicks_over_time", [])
        if len(timeline) >= 6:
            mid         = len(timeline) // 2
            first_half  = sum(d["clicks"] for d in timeline[:mid])
            second_half = sum(d["clicks"] for d in timeline[mid:])
            if first_half > 0:
                pct = round((second_half - first_half) / first_half * 100, 1)
                trend = f"UP +{pct}%" if pct > 0 else f"DOWN {pct}%"
            else:
                trend = "UP (new)" if second_half > 0 else "FLAT"
        else:
            trend = "INSUFFICIENT DATA"

        devices = a.get("devices", {})
        referers = a.get("referers", {})
        top_device   = max(devices,  key=devices.get)  if devices  else "unknown"
        top_referrer = max(referers, key=referers.get) if referers else "direct"

        ph = a.get("peak_hour")
        if ph is not None:
            peak_label = f"{ph % 12 or 12}:00 {'AM' if ph < 12 else 'PM'}"
        else:
            peak_label = "N/A"

        dest_domain = urlparse(link.original_url).hostname or link.original_url

        links_data.append({
            "short_code":    link.short_code,
            "title":         link.title or link.short_code,
            "destination":   dest_domain,
            "is_active":     link.is_active,
            "total_clicks":  total,
            "human_clicks":  human,
            "unique_ips":    unique,
            "bot_pct":       bot_pct,
            "unique_ratio":  unique_ratio,
            "clicks_today":  today,
            "clicks_this_week":  week,
            "clicks_this_month": month,
            "trend_30d":     trend,
            "peak_hour":     peak_label,
            "top_device":    top_device,
            "top_referrer":  top_referrer,
        })

    # Pre-compute winners and losers so the LLM reasons, not calculates
    def winner(key: str) -> str:
        return max(links_data, key=lambda x: x[key])["short_code"]

    def loser(key: str) -> str:
        return min(links_data, key=lambda x: x[key])["short_code"]

    declining     = [l["short_code"] for l in links_data if "DOWN" in l["trend_30d"]]
    zero_this_week = [l["short_code"] for l in links_data if l["clicks_this_week"] == 0 and l["total_clicks"] > 0]
    high_bot      = [l["short_code"] for l in links_data if l["bot_pct"] > 20]
    inactive      = [l["short_code"] for l in links_data if not l["is_active"]]

    return {
        "links": links_data,
        "winners": {
            "most_total_clicks":  winner("total_clicks"),
            "most_unique_reach":  winner("unique_ips"),
            "best_quality":       winner("unique_ratio"),
            "best_momentum":      winner("clicks_this_week"),
            "lowest_bot_rate":    loser("bot_pct"),
        },
        "underperformers": {
            "lowest_total_clicks": loser("total_clicks"),
            "lowest_reach":        loser("unique_ips"),
            "worst_quality":       loser("unique_ratio"),
            "worst_momentum":      loser("clicks_this_week"),
            "highest_bot_rate":    winner("bot_pct"),
        },
        "red_flags": {
            "declining_links":        declining,
            "no_activity_this_week":  zero_this_week,
            "high_bot_rate":          high_bot,
            "inactive_links":         inactive,
        },
    }


async def generate_comparison_insight(
    link_ids: list[str],
    user_id: str,
    db,
) -> str:
    """
    Generate a comparative AI report for 2–4 links.
    Context is injected directly — no tool-call loop needed.
    Returns an error string (not raises) so the router can map to HTTP codes.
    """
    if not llm:
        return "AI Analyst is not configured. Please add GROQ_API_KEY to environment variables."

    context = await _build_comparison_context(link_ids, user_id, db)
    if isinstance(context, str):
        return context   # propagate error string to caller

    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    system_msg = SystemMessage(content=f"""You are an expert link analytics analyst comparing {len(link_ids)} short links.
You have structured analytics data including traffic volume, audience quality, reach, timing, and traffic sources.

Your report MUST address both winners AND underperformers explicitly.

Write exactly 4 paragraphs:
1. Performance Overview — overall winner by volume and reach; and which link is the weakest and why
2. Traffic Quality & Audience — compare bot rates and unique ratios; flag any suspicious or low-quality traffic patterns
3. Momentum & Trends — who is growing, who is stagnating or declining; explicitly call out links with no recent activity
4. Recommendations — 2-3 specific, actionable steps: what to scale up, what to fix, and whether any link should be deprioritized

Rules:
- Refer to links by /<short_code> or their title — never use bare UUIDs
- Ground every claim in the specific numbers from the data provided
- The "winners" and "underperformers" fields pre-compute the factual rankings; use them and focus on explanation
- The "red_flags" field highlights critical issues — address every non-empty flag explicitly
- Use direct, confident language. Avoid hedging phrases like "it seems" or "might possibly"
- Current time: {current_time}""")

    human_msg = HumanMessage(content=f"Comparison data:\n{json.dumps(context, indent=2)}\n\nWrite the comparative analysis report.")

    response = await llm.ainvoke([system_msg, human_msg])
    return response.content


# ── AI Campaign Builder ───────────────────────────────────────────────────────

class ProposedLink(BaseModel):
    original_url: str = Field(description="The original long URL to be shortened.")
    title: str = Field(description="A descriptive title for the link. Infer from URL if not provided.")
    custom_code: str = Field(description="A unique, URL-friendly short code for the link (e.g. 'summershoes'). MUST be generated.")
    utm_source: Optional[str] = Field(None, description="Optional UTM source (e.g., 'facebook', 'newsletter').")
    utm_medium: Optional[str] = Field(None, description="Optional UTM medium (e.g., 'social', 'email').")
    utm_campaign: Optional[str] = Field(None, description="Optional UTM campaign name.")

class ProposedProject(BaseModel):
    name: str = Field(description="The name of the project/campaign.")
    description: str = Field(description="A brief description of the project/campaign.")
    color: str = Field(description="A hex color code for the project, e.g., '#6366f1'.")
    links: list[ProposedLink] = Field(description="A list of links belonging to this project.")

class CampaignProposalResponse(BaseModel):
    projects: list[ProposedProject] = Field(description="A list of projects/campaigns.")
    ai_message: Optional[str] = Field(None, description="If the user asks an irrelevant request, respond to them conversationally here, keeping projects empty.")

class CampaignPromptRequest(BaseModel):
    prompt: str

async def generate_campaign_proposal(prompt: str) -> CampaignProposalResponse:
    """
    Parses a user's natural language request to create a structured campaign.
    Enforces JSON schema via Groq's tool usage / structured outputs.
    """
    if not llm:
        raise ValueError("AI Analyst is not configured. Please add GROQ_API_KEY.")
    
    system_msg = SystemMessage(content="""You are an expert Marketing Campaign Architect. 
Your task is to parse user intents and URLs into a cohesive, structured campaign blueprint.
You MUST use the provided tool to output the structured response. Do not output raw text or markdown JSON.

Guidelines:
1. If the user provides URLs but no project name, intelligently infer a project name from the URL path (e.g. 'Summer Collection') or group them under 'Miscellaneous Campaign'.
2. If the user explicitly describes or implies multiple distinct campaigns, create a separate project object for each.
3. If user wants specific different projects creation, create separate project object for each.
4. Do not hallucinate random unconnected project names.
5. Ensure all URLs provided by the user are properly captured.
6. Provide a nice, vibrant hex color for the project (e.g., '#6366f1', '#ec4899', '#f59e0b', '#10b981').
7. Fill in appropriate titles for the links if they are not provided, based on the URL context.
8. Generate a unique, URL-friendly short code for each link (e.g. 'summershoes'). MUST be generated and MUST be unique across all links and all projects.
9. If the user asks for UTM tags or implies tracking (e.g., 'for Facebook ads', 'email blast'), populate the separate `utm_source`, `utm_medium`, and `utm_campaign` fields appropriately. DO NOT embed them manually into the `original_url`.
10. CRITICAL: If the user's prompt is completely irrelevant to creating URLs or campaigns (e.g., general chat, coding, recipes), leave the projects array empty and provide a polite conversational response in 'ai_message'.
""")
    
    human_msg = HumanMessage(content=prompt)
    
    structured_llm = llm.with_structured_output(CampaignProposalResponse)
    response = await structured_llm.ainvoke([system_msg, human_msg])
    
    return response


