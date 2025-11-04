#!/usr/bin/env python3
"""
ICD-10 Data Import Script
Imports all CID-10 data from CSV, XML, and CNV packages into the database
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from database import get_async_session
from app.services.icd10_comprehensive_import import import_all_icd10_data


async def main():
    """Main import function"""
    print("🏥 Starting ICD-10 data import...")
    
    # Define file paths (in parent directory)
    csv_path = "../CID10CSV.zip"
    xml_path = "../CID10XML.zip"
    cnv_path = "../CID10CNV.zip"
    
    # Check if files exist
    for file_path in [csv_path, xml_path, cnv_path]:
        if not os.path.exists(file_path):
            print(f"❌ Error: {file_path} not found in current directory")
            print("Please ensure all CID-10 ZIP files are in the project root directory")
            return
    
    try:
        # Get database session
        async for db in get_async_session():
            # Import all data
            results = await import_all_icd10_data(db, csv_path, xml_path, cnv_path)
            
            # Print results
            print("\n📊 Import Results:")
            print(f"  CSV Data:")
            for key, value in results.get('csv', {}).items():
                print(f"    {key}: {value} records")
            
            print(f"  XML Data:")
            for key, value in results.get('xml', {}).items():
                print(f"    {key}: {value} records")
            
            print(f"  CNV Data:")
            for key, value in results.get('cnv', {}).items():
                print(f"    {key}: {value} records")
            
            print(f"  Search Index: {results.get('search_index', 0)} entries")
            
            print("\n✅ ICD-10 data import completed successfully!")
            break
            
    except Exception as e:
        print(f"❌ Error during import: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
