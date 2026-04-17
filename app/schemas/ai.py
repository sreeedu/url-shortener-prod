from pydantic import BaseModel, Field
from typing import Optional

class ProposedLink(BaseModel):
    original_url: str = Field(description="The original URL destination. Extract this from the user prompt.")
    title: str = Field(description="A short, descriptive title for the link.")
    custom_code: Optional[str] = Field(None, description="Optional custom short code alias (only letters, numbers, hyphens). Leave null if none is requested.")

    class Config:
        json_schema_extra = {
            "example": {
                "original_url": "https://example.com/summer-sale",
                "title": "Summer Sale 2026",
                "custom_code": "summer26"
            }
        }

class ProposedProject(BaseModel):
    name: str = Field(description="Name of the project or campaign. If the user doesn't mention a project name, infer a suitable default name based on their URLs or text.")
    description: str = Field(description="A brief description of what this project is for.")
    color: str = Field(description="A hex color code representing the project, e.g. '#3b82f6'. Pick a random recognizable hex color if not specified.")
    links: list[ProposedLink] = Field(description="List of links to be created inside this project. Can be empty if no specific links were mentioned.")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Summer Marketing Campaign",
                "description": "Links for the upcoming summer marketing push.",
                "color": "#ec4899",
                "links": []
            }
        }

class CampaignProposalResponse(BaseModel):
    projects: list[ProposedProject] = Field(description="List of projects to create based on the user's prompt.")
