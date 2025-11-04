"""
ICD-10 Data Import Service
Imports data from CID10CSV.zip files into the database
"""

import zipfile
import csv
import io
import re
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.icd10 import (
    ICD10Chapter, ICD10Group, ICD10Category, ICD10Subcategory, ICD10SearchIndex
)


def normalize_text(text: str) -> str:
    """Normalize text for search indexing"""
    if not text:
        return ""
    
    # Remove accents and special characters
    text = text.lower()
    text = re.sub(r'[àáâãäå]', 'a', text)
    text = re.sub(r'[èéêë]', 'e', text)
    text = re.sub(r'[ìíîï]', 'i', text)
    text = re.sub(r'[òóôõö]', 'o', text)
    text = re.sub(r'[ùúûü]', 'u', text)
    text = re.sub(r'[ç]', 'c', text)
    text = re.sub(r'[ñ]', 'n', text)
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


async def import_chapters(db: AsyncSession, csv_data: str) -> int:
    """Import ICD-10 chapters from CSV data"""
    # Clear existing data
    await db.execute(delete(ICD10Chapter))
    
    reader = csv.DictReader(io.StringIO(csv_data), delimiter=';')
    chapters = []
    
    for row in reader:
        if not row.get('CLASSIF'):
            continue
            
        chapter = ICD10Chapter(
            code=row['CLASSIF'].strip(),
            description=row.get('DESCRICAO', '').strip(),
            description_short=row.get('DESCRABREV', '').strip() or None
        )
        chapters.append(chapter)
    
    db.add_all(chapters)
    await db.commit()
    return len(chapters)


async def import_groups(db: AsyncSession, csv_data: str) -> int:
    """Import ICD-10 groups from CSV data"""
    await db.execute(delete(ICD10Group))
    
    reader = csv.DictReader(io.StringIO(csv_data), delimiter=';')
    groups = []
    
    for row in reader:
        if not row.get('CLASSIF'):
            continue
            
        group = ICD10Group(
            code=row['CLASSIF'].strip(),
            description=row.get('DESCRICAO', '').strip(),
            description_short=row.get('DESCRABREV', '').strip() or None,
            chapter_code=row.get('CAPITULO', '').strip() or None
        )
        groups.append(group)
    
    db.add_all(groups)
    await db.commit()
    return len(groups)


async def import_categories(db: AsyncSession, csv_data: str) -> int:
    """Import ICD-10 categories from CSV data"""
    await db.execute(delete(ICD10Category))
    
    reader = csv.DictReader(io.StringIO(csv_data), delimiter=';')
    categories = []
    
    for row in reader:
        if not row.get('CLASSIF'):
            continue
            
        category = ICD10Category(
            code=row['CLASSIF'].strip(),
            description=row.get('DESCRICAO', '').strip(),
            description_short=row.get('DESCRABREV', '').strip() or None,
            reference=row.get('REFER', '').strip() or None,
            exclusions=row.get('EXCLUIDOS', '').strip() or None,
            group_code=row.get('GRUPO', '').strip() or None
        )
        categories.append(category)
    
    db.add_all(categories)
    await db.commit()
    return len(categories)


async def import_subcategories(db: AsyncSession, csv_data: str) -> int:
    """Import ICD-10 subcategories from CSV data"""
    await db.execute(delete(ICD10Subcategory))
    
    reader = csv.DictReader(io.StringIO(csv_data), delimiter=';')
    subcategories = []
    
    for row in reader:
        if not row.get('CLASSIF'):
            continue
            
        subcategory = ICD10Subcategory(
            code=row['CLASSIF'].strip(),
            description=row.get('DESCRICAO', '').strip(),
            description_short=row.get('DESCRABREV', '').strip() or None,
            sex_restriction=row.get('RESTRSEXO', '').strip() or None,
            cause_of_death=row.get('CAUSAOBITO', '').strip().upper() == 'S',
            reference=row.get('REFER', '').strip() or None,
            exclusions=row.get('EXCLUIDOS', '').strip() or None,
            category_code=row.get('CAT', '').strip() or None
        )
        subcategories.append(subcategory)
    
    db.add_all(subcategories)
    await db.commit()
    return len(subcategories)


async def build_search_index(db: AsyncSession) -> int:
    """Build search index for full-text search"""
    await db.execute(delete(ICD10SearchIndex))
    
    search_entries = []
    
    # Index chapters
    chapters = (await db.execute(select(ICD10Chapter))).scalars().all()
    for chapter in chapters:
        search_text = f"{chapter.code} {normalize_text(chapter.description)} {normalize_text(chapter.description_short or '')}"
        search_entries.append(ICD10SearchIndex(
            code=chapter.code,
            description=chapter.description,
            search_text=search_text,
            level='chapter'
        ))
    
    # Index groups
    groups = (await db.execute(select(ICD10Group))).scalars().all()
    for group in groups:
        search_text = f"{group.code} {normalize_text(group.description)} {normalize_text(group.description_short or '')}"
        search_entries.append(ICD10SearchIndex(
            code=group.code,
            description=group.description,
            search_text=search_text,
            level='group',
            parent_code=group.chapter_code
        ))
    
    # Index categories
    categories = (await db.execute(select(ICD10Category))).scalars().all()
    for category in categories:
        search_text = f"{category.code} {normalize_text(category.description)} {normalize_text(category.description_short or '')}"
        search_entries.append(ICD10SearchIndex(
            code=category.code,
            description=category.description,
            search_text=search_text,
            level='category',
            parent_code=category.group_code
        ))
    
    # Index subcategories
    subcategories = (await db.execute(select(ICD10Subcategory))).scalars().all()
    for subcategory in subcategories:
        search_text = f"{subcategory.code} {normalize_text(subcategory.description)} {normalize_text(subcategory.description_short or '')}"
        search_entries.append(ICD10SearchIndex(
            code=subcategory.code,
            description=subcategory.description,
            search_text=search_text,
            level='subcategory',
            parent_code=subcategory.category_code
        ))
    
    db.add_all(search_entries)
    await db.commit()
    return len(search_entries)


async def import_icd10_from_zip(db: AsyncSession, zip_path: str) -> Dict[str, int]:
    """Import all ICD-10 data from CID10CSV.zip"""
    results = {}
    
    with zipfile.ZipFile(zip_path, 'r') as zip_file:
        # Import chapters
        if 'CID-10-CAPITULOS.CSV' in zip_file.namelist():
            csv_data = zip_file.read('CID-10-CAPITULOS.CSV').decode('utf-8', errors='ignore')
            results['chapters'] = await import_chapters(db, csv_data)
        
        # Import groups
        if 'CID-10-GRUPOS.CSV' in zip_file.namelist():
            csv_data = zip_file.read('CID-10-GRUPOS.CSV').decode('utf-8', errors='ignore')
            results['groups'] = await import_groups(db, csv_data)
        
        # Import categories
        if 'CID-10-CATEGORIAS.CSV' in zip_file.namelist():
            csv_data = zip_file.read('CID-10-CATEGORIAS.CSV').decode('utf-8', errors='ignore')
            results['categories'] = await import_categories(db, csv_data)
        
        # Import subcategories
        if 'CID-10-SUBCATEGORIAS.CSV' in zip_file.namelist():
            csv_data = zip_file.read('CID-10-SUBCATEGORIAS.CSV').decode('utf-8', errors='ignore')
            results['subcategories'] = await import_subcategories(db, csv_data)
    
    # Build search index
    results['search_entries'] = await build_search_index(db)
    
    return results
