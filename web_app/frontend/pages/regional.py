"""
THIWASCO Regional Management Page
Multi-zone water distribution and maintenance oversight - pure UI logic only
"""

import streamlit as st
from ..components import render_page_heading, render_section_card

def render_regional_management(data_service):
    """Render regional management page"""
    # Page header
    render_page_heading(
        "Regional Management",
        "Multi-zone water distribution and maintenance oversight"
    )
    
    # Get regional data from backend
    regional_data = data_service.get_regional_data()
    
    render_section_card(
        "Regional Status",
        "Detailed breakdown by geographical area including zone assignments"
    )
    
    if not regional_data.empty:
        # Reorder columns to show zone_id prominently
        column_order = ['zone_id', 'meter_id', 'location', 'total_readings', 'leak_count']
        available_columns = [col for col in column_order if col in regional_data.columns]
        remaining_columns = [col for col in regional_data.columns if col not in available_columns]
        final_columns = available_columns + remaining_columns
        
        regional_data_ordered = regional_data[final_columns]
        
        st.dataframe(regional_data_ordered, use_container_width=True, hide_index=True)
        
        # Data source information
        with st.expander("Data Source Information", expanded=False):
            st.markdown("""
            **Data Source:** Backend Database & Sample Data
            
            **Data Flow:**
            1. **Primary:** Database meter summary table (if available)
            2. **Fallback:** Sample data for demonstration
            
            **Zone ID Generation:**
            - **Database:** Uses zone_id from meters table
            - **Sample:** Generated from meter_id (e.g., HW-THK-001 -> ZONE-001)
            
            **Columns:**
            - **zone_id:** Geographic zone identifier
            - **meter_id:** Unique Honeywell meter identifier  
            - **location:** Physical installation location
            - **total_readings:** Number of sensor readings recorded
            - **leak_count:** Number of leak detections for this meter
            """)
    else:
        st.info("No regional data available")
