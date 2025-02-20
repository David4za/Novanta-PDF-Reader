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

def get_all_parts(text):
    """
    Extracts all PART IDs and their DESCRIPTIONS from the parts table in the text.
    It finds the header line (which contains "PART ID" and "DESCRIPTION"),
    then collects subsequent lines until "Country MFG:" is encountered.
    
    It also merges a line that is purely numeric with the previous row,
    since your data shows those extra numeric lines.
    """
    lines = text.splitlines()
    header_index = None
    for i, line in enumerate(lines):
        if "PART ID" in line and "DESCRIPTION" in line:
            header_index = i
            break
    if header_index is None:
        return []
    
    # Gather all rows from after the header until "Country MFG:" is found
    rows = []
    i = header_index + 1
    while i < len(lines):
        if "Country MFG:" in lines[i]:
            break
        if not lines[i].strip():
            i += 1
            continue
        # If the line is purely numeric (like "00003"), append it to the previous row
        if re.match(r'^\d+$', lines[i].strip()):
            if rows:
                rows[-1] = rows[-1] + " " + lines[i].strip()
            i += 1
            continue
        rows.append(lines[i].strip())
        i += 1

    parts = []
    for row in rows:
        tokens = row.split()
        if len(tokens) < 3:
            continue
        # In your table the columns are: ORDERED, SHIPPED (merged with PART ID), DESCRIPTION, PRICE, ...
        # Remove the leading numeric from token[1] to extract the actual PART ID.
        part_token = tokens[1]
        part_id = re.sub(r'^\d+\.\d+', '', part_token)
        
        # The description is all tokens from index 2 until the first token starting with "$"
        desc_tokens = []
        for token in tokens[2:]:
            if token.startswith('$'):
                break
            desc_tokens.append(token)
        description = " ".join(desc_tokens)
        parts.append((part_id, description))
    return parts

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
    Extract Invoice ID, PACK LIST ID, all PART IDs with their DESCRIPTIONS,
    and Harmonization Code from the PDF.
    """
    invoice_data = {
        'Invoice ID': None,
        'PACK LIST ID': None,
        'Harmonization Code': None,
        'PARTS': []  # List of tuples: (PART ID, DESCRIPTION)
    }
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            # Extract Invoice ID
            if invoice_data['Invoice ID'] is None:
                match = re.search(r'Invoice ID:\s*(\S+)', text)
                if match:
                    invoice_data['Invoice ID'] = match.group(1)
            
            # Extract Harmonization Code
            if invoice_data['Harmonization Code'] is None:
                match = re.search(r'Harmonization Code:\s*([\d\.]+)', text)
                if match:
                    invoice_data['Harmonization Code'] = match.group(1)
            
            lines = text.splitlines()
            
            # Extract PACK LIST ID
            pack_list_id = get_pack_list_id_from_tokens(lines)
            if pack_list_id and invoice_data['PACK LIST ID'] is None:
                invoice_data['PACK LIST ID'] = pack_list_id

            # Extract all parts from the table
            parts = get_all_parts(text)
            if parts:
                invoice_data['PARTS'].extend(parts)
            
            # If all key fields are found, we can break out early
            if (invoice_data['Invoice ID'] and invoice_data['Harmonization Code'] and
                invoice_data['PACK LIST ID'] and invoice_data['PARTS']):
                break
    
    return invoice_data

# Streamlit UI
st.title("Novanta PDF Reader")
st.write("Upload a PDF")

uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

if uploaded_file is not None:
    try:
        invoice_data = extract_invoice_data(uploaded_file)
        
        # Display basic invoice data excluding parts
        basic_data = {
            "Invoice ID": invoice_data["Invoice ID"],
            "PACK LIST ID": invoice_data["PACK LIST ID"],
            "Harmonization Code": invoice_data["Harmonization Code"],
        }
        df_basic = pd.DataFrame([basic_data])
        st.markdown("### Invoice Data")
        st.dataframe(df_basic)
        
        # Create a DataFrame for parts with two columns: PART ID and DESCRIPTION.
        if invoice_data["PARTS"]:
            parts_df = pd.DataFrame(invoice_data["PARTS"], columns=["PART ID", "DESCRIPTION"])
            st.markdown("### Parts Data")
            st.dataframe(parts_df)
        else:
            st.write("No parts found.")
        
    except Exception as e:
        st.error(f"An error occurred while processing the PDF: {e}")
