import streamlit as st
import pdfplumber
import re
import pandas as pd

def merge_header_tokens(tokens):
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

def extract_invoice_data(pdf_file):
    invoice_data_list = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            invoice_data = {
                'Invoice ID': None,
                'PACK LIST ID': None,
                'PART ID': None,
                'DESCRIPTION': None,
                'Harmonization Code': None
            }
            match = re.search(r'Invoice ID:\s*(\S+)', text)
            if match:
                invoice_data['Invoice ID'] = match.group(1)
            match = re.search(r'Harmonization Code:\s*([\d\.]+)', text)
            if match:
                invoice_data['Harmonization Code'] = match.group(1)
            lines = text.splitlines()
            for line in lines:
                if "PACK LIST ID" in line:
                    parts = line.split()
                    if len(parts) > 1:
                        invoice_data['PACK LIST ID'] = parts[-1]
                if "PART ID" in line:
                    parts = line.split()
                    if len(parts) > 1:
                        invoice_data['PART ID'] = parts[-1]
                if "DESCRIPTION" in line:
                    parts = line.split(maxsplit=1)
                    if len(parts) > 1:
                        invoice_data['DESCRIPTION'] = parts[1]
            if any(invoice_data.values()):
                invoice_data_list.append(invoice_data)
    return invoice_data_list

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
