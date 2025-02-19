import streamlit as st
import pdfplumber
import re
import pandas as pd

def merge_header_tokens(tokens):
    """
    Merge consecutive tokens for multi-word headers.
    Merge "PACK", "LIST", "ID" to "PACK LIST ID" and "PART", "ID" to "PART ID".
    """
    merged = []
    i = 0
    while i < len(tokens):
        if i+2 < len(tokens) and tokens[i] == "PACK" and tokens[i+1] == "LIST" and tokens[i+2] == "ID":
            merged.append("PACK LIST ID")
            i += 3
        elif i+1 < len(tokens) and tokens[i] == "PART" and tokens[i+1] == "ID":
            merged.append("PART ID")
            i += 2
        else:
            merged.append(tokens[i])
            i += 1
    return merged

def merge_numeric_tokens(tokens):
    """
    Merge tokens that appear to be a split number.
    For example, merge ['25.0', '0'] into ['25.00'].
    """
    merged = []
    skip_next = False
    for i in range(len(tokens)):
        if skip_next:
            skip_next = False
            continue
        if i < len(tokens) - 1 and re.match(r'^\d+\.\d*$', tokens[i]) and re.match(r'^\d+$', tokens[i+1]):
            merged.append(tokens[i] + tokens[i+1])
            skip_next = True
        else:
            merged.append(tokens[i])
    return merged

def get_part_description_from_tokens(text_lines):
    """
    Extract PART ID and DESCRIPTION using tokenization.
    Looks for the header line that contains "PART ID" and returns
    the value from the data line at the expected indices.
    """
    for i, line in enumerate(text_lines):
        if "PART ID" in line:
            header_line = line
            data_line = text_lines[i+1] if i+1 < len(text_lines) else ""
            
            header_tokens = merge_header_tokens(header_line.split())
            
            raw_data_tokens = data_line.split()
            fixed_data_tokens = []
            for token in raw_data_tokens:
                # Split tokens like "25.00MDI1PRD17C4-EQ" into separate parts
                match = re.match(r'^(\d+\.\d+)([A-Za-z0-9\-]+)$', token)
                if match:
                    fixed_data_tokens.extend([match.group(1), match.group(2)])
                else:
                    fixed_data_tokens.append(token)
            data_tokens = merge_numeric_tokens(fixed_data_tokens)
            
            # Assuming from our debug: PART ID is at index 2 and DESCRIPTION at index 3.
            if len(data_tokens) >= 4:
                return data_tokens[2], data_tokens[3]
    return None, None

def get_pack_list_id_from_tokens(text_lines):
    """
    Extract PACK LIST ID using tokenization.
    Looks for the header line that contains "PACK LIST ID" and then
    retrieves the corresponding value from the data row.
    """
    for i, line in enumerate(text_lines):
        if "PACK" in line and "LIST" in line and "ID" in line:
            header_line = line
            data_line = text_lines[i+1] if i+1 < len(text_lines) else ""
            
            header_tokens = merge_header_tokens(header_line.split())
            
            raw_data_tokens = data_line.split()
            fixed_data_tokens = []
            for token in raw_data_tokens:
                match = re.match(r'^(\d+\.\d+)([A-Za-z0-9\-]+)$', token)
                if match:
                    fixed_data_tokens.extend([match.group(1), match.group(2)])
                else:
                    fixed_data_tokens.append(token)
            data_tokens = merge_numeric_tokens(fixed_data_tokens)
            
            if "PACK LIST ID" in header_tokens:
                idx = header_tokens.index("PACK LIST ID")
                if idx < len(data_tokens):
                    return data_tokens[idx]
    return None

def extract_invoice_data(pdf_path):
    """
    Extract Invoice ID, PACK LIST ID, PART ID, DESCRIPTION, and Harmonization Code from the PDF.
    """
    invoice_data = {
        'Invoice ID': None,
        'PACK LIST ID': None,
        'PART ID': None,
        'DESCRIPTION': None,
        'Harmonization Code': None
    }
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            
            # Extract Invoice ID from text
            if invoice_data['Invoice ID'] is None:
                match = re.search(r'Invoice ID:\s*(\S+)', text)
                if match:
                    invoice_data['Invoice ID'] = match.group(1)
            
            # Extract Harmonization Code from text
            if invoice_data['Harmonization Code'] is None:
                match = re.search(r'Harmonization Code:\s*([\d\.]+)', text)
                if match:
                    invoice_data['Harmonization Code'] = match.group(1)
            
            # Token-based extraction for PART ID, DESCRIPTION, and PACK LIST ID.
            lines = text.splitlines()
            
            # Extract PART ID and DESCRIPTION
            part_id, description = get_part_description_from_tokens(lines)
            if part_id and description:
                invoice_data['PART ID'] = part_id
                invoice_data['DESCRIPTION'] = description
            
            # Extract PACK LIST ID
            pack_list_id = get_pack_list_id_from_tokens(lines)
            if pack_list_id:
                invoice_data['PACK LIST ID'] = pack_list_id
            
            # Break early if all fields are found
            if all(invoice_data.values()):
                break
    
    return invoice_data

# Streamlit App
st.title("PDF Invoice Reader")
st.markdown("Upload a PDF file, and we will extract the key invoice data for you.")

uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])

if uploaded_file is not None:
    with st.spinner("Processing file..."):
        invoice_data_list = extract_invoice_data(uploaded_file)
        if invoice_data_list:
            df = pd.DataFrame(invoice_data_list)
            if not df.empty:
                st.success("Extraction complete!")
                st.dataframe(df.style.set_properties(**{'text-align': 'left'}))
            else:
                st.error("Extracted data is empty. Please check the PDF content.")
        else:
            st.error("No valid invoice data found in the PDF.")
