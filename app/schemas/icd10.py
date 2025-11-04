"""
ICD-10 Pydantic schemas for API responses
"""

import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class ICD10ChapterResponse(BaseModel):
    id: int
    code: str
    description: str
    description_short: Optional[str] = None
    created_at: datetime.datetime
    
    class Config:
        from_attributes = True


class ICD10GroupResponse(BaseModel):
    id: int
    code: str
    description: str
    description_short: Optional[str] = None
    chapter_code: Optional[str] = None
    created_at: datetime.datetime
    
    class Config:
        from_attributes = True


class ICD10CategoryResponse(BaseModel):
    id: int
    code: str
    description: str
    description_short: Optional[str] = None
    reference: Optional[str] = None
    exclusions: Optional[str] = None
    group_code: Optional[str] = None
    created_at: datetime.datetime
    
    class Config:
        from_attributes = True


class ICD10SubcategoryResponse(BaseModel):
    id: int
    code: str
    description: str
    description_short: Optional[str] = None
    sex_restriction: Optional[str] = None
    cause_of_death: bool = False
    reference: Optional[str] = None
    exclusions: Optional[str] = None
    category_code: Optional[str] = None
    created_at: datetime.datetime
    
    class Config:
        from_attributes = True


class ICD10SearchResult(BaseModel):
    """Unified search result for any ICD-10 level"""
    code: str
    description: str
    description_short: Optional[str] = None
    level: str  # 'chapter', 'group', 'category', 'subcategory'
    parent_code: Optional[str] = None
    
    class Config:
        from_attributes = True


class ICD10SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200, description="Search query")
    level: Optional[str] = Field(None, description="Filter by level: chapter, group, category, subcategory")
    limit: int = Field(20, ge=1, le=100, description="Maximum number of results")
    include_death_codes: bool = Field(True, description="Include codes that can be cause of death")


class ICD10SuggestionRequest(BaseModel):
    symptoms: str = Field(..., min_length=1, max_length=500, description="Symptoms or clinical description")
    limit: int = Field(10, ge=1, le=50, description="Maximum number of suggestions")
