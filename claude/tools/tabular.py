import tabula
import pandas as pd
import logging
from pathlib import Path
import argparse

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def extract_tables_from_pdf(pdf_path: str, pages: str = 'all', multiple_tables: bool = True, 
                          lattice: bool = True, stream: bool = True, guess: bool = True,
                          password: str = None, area: list = None, relative_area: bool = False,
                          encoding: str = 'utf-8') -> list:
    """
    Extract tables from PDF using tabula-py.
    
    Args:
        pdf_path (str): Path to PDF file
        pages (str): Page numbers to extract tables from (e.g., '1,2,3' or 'all')
        multiple_tables (bool): Whether to extract multiple tables per page
        lattice (bool): Whether to use lattice mode (for tables with borders)
        stream (bool): Whether to use stream mode (for tables without borders)
        guess (bool): Whether to guess table structure
        password (str): PDF password if encrypted
        area (list): Table area to extract [top, left, bottom, right]
        relative_area (bool): Whether area coordinates are relative to page size
        encoding (str): Output encoding
        
    Returns:
        list: List of extracted tables as DataFrames
    """
    try:
        # Read tables from PDF
        dfs = tabula.read_pdf(
            pdf_path,
            pages=pages,
            multiple_tables=multiple_tables,
            lattice=lattice,
            stream=stream,
            guess=guess,
            password=password,
            area=area,
            relative_area=relative_area,
            encoding=encoding
        )
        
        logger.info(f"Successfully extracted {len(dfs)} tables from {pdf_path}")
        return dfs
        
    except Exception as e:
        logger.error(f"Error extracting tables from PDF: {str(e)}")
        raise

def save_tables_to_csv(dfs: list, output_dir: str, prefix: str = 'table_') -> None:
    """
    Save extracted tables to CSV files.
    
    Args:
        dfs (list): List of DataFrames to save
        output_dir (str): Directory to save CSV files
        prefix (str): Prefix for output filenames
    """
    try:
        # Create output directory if it doesn't exist
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # Save each table to a separate CSV file
        for i, df in enumerate(dfs):
            output_path = Path(output_dir) / f"{prefix}{i+1}.csv"
            df.to_csv(output_path, index=False, encoding='utf-8')
            logger.info(f"Saved table {i+1} to {output_path}")
            
    except Exception as e:
        logger.error(f"Error saving tables to CSV: {str(e)}")
        raise

def main():
    parser = argparse.ArgumentParser(description='Extract tables from PDFs using tabula-py')
    parser.add_argument('--input', required=True, help='Input PDF file path')
    parser.add_argument('--output-dir', required=True, help='Output directory for CSV files')
    parser.add_argument('--pages', default='all', help='Page numbers to extract (e.g., "1,2,3" or "all")')
    parser.add_argument('--multiple-tables', action='store_true', help='Extract multiple tables per page')
    parser.add_argument('--lattice', action='store_true', help='Use lattice mode (for tables with borders)')
    parser.add_argument('--stream', action='store_true', help='Use stream mode (for tables without borders)')
    parser.add_argument('--guess', action='store_true', help='Guess table structure')
    parser.add_argument('--password', help='PDF password if encrypted')
    parser.add_argument('--area', help='Table area to extract [top,left,bottom,right]')
    parser.add_argument('--relative-area', action='store_true', help='Use relative area coordinates')
    parser.add_argument('--encoding', default='utf-8', help='Output encoding')
    parser.add_argument('--prefix', default='table_', help='Prefix for output filenames')
    
    args = parser.parse_args()
    
    # Parse area if provided
    area = None
    if args.area:
        area = [float(x) for x in args.area.split(',')]
    
    try:
        # Extract tables
        dfs = extract_tables_from_pdf(
            args.input,
            pages=args.pages,
            multiple_tables=args.multiple_tables,
            lattice=args.lattice,
            stream=args.stream,
            guess=args.guess,
            password=args.password,
            area=area,
            relative_area=args.relative_area,
            encoding=args.encoding
        )
        
        # Save tables to CSV
        save_tables_to_csv(dfs, args.output_dir, args.prefix)
        
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        raise

if __name__ == '__main__':
    main()