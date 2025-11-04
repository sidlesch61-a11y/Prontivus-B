"""
ICD-10 Database Models
Based on analysis of CID10CSV.zip, CID10XML.zip, and CID10CNV.zip files
"""

import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Index
from database import Base


class ICD10Chapter(Base):
    """
    ICD-10 Chapters (CID-10-CAPITULOS.CSV)
    """
    __tablename__ = "icd10_chapters"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, nullable=False)  # e.g., "A00-B99" (index defined in __table_args__)
    description = Column(Text, nullable=False)
    description_short = Column(String(200), nullable=True)
    start_code = Column(String(10), nullable=True)  # e.g., "A00"
    end_code = Column(String(10), nullable=True)    # e.g., "B99"
    chapter_number = Column(Integer, nullable=True)  # Chapter number
    
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.now, nullable=False)
    
    # Index for search performance
    __table_args__ = (
        Index('ix_icd10_chapters_code', 'code'),
    )


class ICD10Group(Base):
    """
    ICD-10 Groups (CID-10-GRUPOS.CSV)
    """
    __tablename__ = "icd10_groups"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, nullable=False)  # e.g., "A00-A09" (index defined in __table_args__)
    description = Column(Text, nullable=False)
    description_short = Column(String(200), nullable=True)
    chapter_code = Column(String(10), nullable=True)  # Reference to chapter (index defined in __table_args__)
    start_code = Column(String(10), nullable=True)  # e.g., "A00"
    end_code = Column(String(10), nullable=True)    # e.g., "A09"
    
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.now, nullable=False)
    
    __table_args__ = (
        Index('ix_icd10_groups_code', 'code'),
        Index('ix_icd10_groups_chapter', 'chapter_code'),
    )


class ICD10Category(Base):
    """
    ICD-10 Categories (CID-10-CATEGORIAS.CSV)
    Main diagnostic categories
    """
    __tablename__ = "icd10_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, nullable=False)  # e.g., "A00" (index defined in __table_args__)
    description = Column(Text, nullable=False)
    description_short = Column(String(200), nullable=True)
    reference = Column(Text, nullable=True)
    exclusions = Column(Text, nullable=True)
    group_code = Column(String(10), nullable=True)  # Reference to group (index defined in __table_args__)
    
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.now, nullable=False)
    
    __table_args__ = (
        Index('ix_icd10_categories_code', 'code'),
        Index('ix_icd10_categories_group', 'group_code'),
    )


class ICD10Subcategory(Base):
    """
    ICD-10 Subcategories (CID-10-SUBCATEGORIAS.CSV)
    Specific diagnostic codes with 4th digit
    """
    __tablename__ = "icd10_subcategories"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, nullable=False)  # e.g., "A00.0" (index defined in __table_args__)
    description = Column(Text, nullable=False)
    description_short = Column(String(200), nullable=True)
    sex_restriction = Column(String(50), nullable=True)  # RESTRSEXO
    cause_of_death = Column(Boolean, default=False, nullable=False)  # CAUSAOBITO
    reference = Column(Text, nullable=True)
    exclusions = Column(Text, nullable=True)
    category_code = Column(String(10), nullable=True)  # Reference to category (index defined in __table_args__)
    
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.now, nullable=False)
    
    __table_args__ = (
        Index('ix_icd10_subcategories_code', 'code'),
        Index('ix_icd10_subcategories_category', 'category_code'),
        Index('ix_icd10_subcategories_death', 'cause_of_death'),
    )


class ICD10SearchIndex(Base):
    """
    Search index for full-text search across ICD-10 codes and descriptions
    """
    __tablename__ = "icd10_search_index"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), nullable=False)  # index defined in __table_args__ if needed
    description = Column(Text, nullable=False)
    search_text = Column(Text, nullable=False)  # Normalized text for search (index defined in __table_args__)
    level = Column(String(20), nullable=False)  # 'chapter', 'group', 'category', 'subcategory' (index defined in __table_args__)
    parent_code = Column(String(10), nullable=True)  # index defined in __table_args__ if needed
    
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.now, nullable=False)
    
    __table_args__ = (
        Index('ix_icd10_search_code', 'code'),
        Index('ix_icd10_search_text', 'search_text'),
        Index('ix_icd10_search_level', 'level'),
        Index('ix_icd10_search_parent', 'parent_code'),
    )
