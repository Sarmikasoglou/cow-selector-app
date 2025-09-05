# cow_selector_app.py
import streamlit as st
import pandas as pd
import plotly.express as px
import re

st.set_page_config(page_title="MooSelect", layout="wide")
st.title("🐄 MooSelect")

uploaded_file = st.file_uploader("Upload your farm CSV file", type=["csv"])

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    st.success(f"Loaded {len(df)} cows from the file ✅")
    st.write("### Preview of your data")
    st.dataframe(df.head())

    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    categorical_cols = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
    all_cols = list(df.columns)

    # Identify boolean-like columns present in CSV
    bool_cols = []
    for c in df.columns:
        unique_vals = df[c].dropna().unique()
        if set(unique_vals).issubset({True, False}) or set(unique_vals).issubset({True}):
            bool_cols.append(c)

    # Initialize session state
    if "filtered_df" not in st.session_state:
        st.session_state.filtered_df = df.copy()
    if "filter_input" not in st.session_state:
        st.session_state.filter_input = ""
    if "bool_filters" not in st.session_state:
        st.session_state.bool_filters = {col: (True, True) for col in bool_cols}

    st.write("### Enter your numeric/categorical filter conditions")
    st.markdown(
        "Examples:\n"
        "`30 <= DIM <= 70 AND FCM > 30`\n"
        "`EART != 20017, 20022`\n"
        "`(30 <= DIM <= 70 AND FCM > 30) OR LAC = 3`\n\n"
        "Operators supported: `>`, `<`, `>=`, `<=`, `=`, `!=`, ranges (`a <= col <= b`), and comma-separated lists\n"
        "Combine conditions with `AND` / `OR` and parentheses."
    )

    filter_input = st.text_area("Filter:", value=st.session_state.filter_input)
    st.session_state.filter_input = filter_input

    # -------- Boolean filter checkboxes --------
    st.write("### Boolean filters (check to include True / Blank values)")
    bool_filters = {}
    for col in bool_cols:
        include_true = st.checkbox(f"{col} = True", value=st.session_state.bool_filters[col][0])
        include_blank = st.checkbox(f"{col} = Blank", value=st.session_state.bool_filters[col][1])
        bool_filters[col] = (include_true, include_blank)
    st.session_state.bool_filters = bool_filters

    # -------- Filter parser --------
    def parse_condition(df, cond):
        cond = cond.strip()

        # Exclude multiple numeric values without brackets: col != val1, val2, val3
        m = re.match(r'(\w+)\s*!=\s*([\d\., ]+)', cond)
        if m:
            col, vals = m.group(1), m.group(2)
            if col not in df.columns:
                return pd.Series([False]*len(df))
            val_list = [float(v.strip()) for v in vals.split(",")]
            return ~df[col].isin(val_list)

        # Include multiple numeric values without brackets: col = val1, val2, val3
        m = re.match(r'(\w+)\s*=\s*([\d\., ]+)', cond)
        if m:
            col, vals = m.group(1), m.group(2)
            if col not in df.columns:
                return pd.Series([False]*len(df))
            val_list = [float(v.strip()) for v in vals.split(",")]
            return df[col].isin(val_list)

        # Mathematical range: a <= col <= b
        m = re.match(r'([\d\.]+)\s*<=\s*(\w+)\s*<=\s*([\d\.]+)', cond)
        if m:
            val1, col, val2 = float(m.group(1)), m.group(2), float(m.group(3))
            if col not in df.columns:
                return pd.Series([False]*len(df))
            df[col] = pd.to_numeric(df[col], errors='coerce')
            return (df[col] >= val1) & (df[col] <= val2)

        # Numeric operators
        m = re.match(r'(\w+)\s*(>=|<=|=|!=|>|<)\s*([\d\.]+)', cond)
        if m:
            col, op, val = m.group(1), m.group(2), float(m.group(3))
            if col not in df.columns:
                return pd.Series([False]*len(df))
            df[col] = pd.to_numeric(df[col], errors='coerce')
            if op == ">": return df[col] > val
            if op == "<": return df[col] < val
            if op == ">=": return df[col] >= val
            if op == "<=": return df[col] <= val
            if op == "=": return df[col] == val
            if op == "!=": return df[col] != val

        # Categorical equality
        m = re.match(r'(\w+)\s*=\s*(.+)', cond)
        if m:
            col, val = m.group(1), m.group(2).strip()
            if col not in df.columns:
                return pd.Series([False]*len(df))
            return df[col].astype(str) == val

        return pd.Series([False]*len(df))

    def evaluate_filter(df, expr):
        expr = expr.strip()
        if expr.startswith("(") and expr.endswith(")"):
            expr = expr[1:-1].strip()
        # Split top-level OR
        or_parts = re.split(r'\bOR\b', expr, flags=re.IGNORECASE)
        if len(or_parts) > 1:
            mask = pd.Series([False]*len(df))
            for part in or_parts:
                mask = mask | evaluate_filter(df, part)
            return mask
        # Split top-level AND
        and_parts = re.split(r'\bAND\b', expr, flags=re.IGNORECASE)
        if len(and_parts) > 1:
            mask = pd.Series([True]*len(df))
            for part in and_parts:
                mask = mask & evaluate_filter(df, part)
            return mask
        return parse_condition(df, expr)

    def apply_bool_filters(df, filters):
        mask = pd.Series([True]*len(df))
        for col, (inc_true, inc_blank) in filters.items():
            col_mask = pd.Series([False]*len(df))
            if inc_true:
                col_mask = col_mask | (df[col] == True)
            if inc_blank:
                col_mask = col_mask | df[col].isna() | (df[col] == "")
            mask = mask & col_mask
        return mask

    # -------- Apply / Reset buttons --------
    col1, col2 = st.columns(2)
    with col1:
        apply = st.button("Apply Filters")
    with col2:
        reset = st.button("Reset Filters")

    if reset:
        st.session_state.filtered_df = df.copy()
        st.session_state.filter_input = ""
        st.session_state.bool_filters = {col: (True, True) for col in bool_cols}

    if apply:
        filtered_df = df.copy()
        if st.session_state.filter_input.strip():
            mask = evaluate_filter(filtered_df, st.session_state.filter_input)
            filtered_df = filtered_df[mask]
        if bool_cols:
            bool_mask = apply_bool_filters(filtered_df, st.session_state.bool_filters)
            filtered_df = filtered_df[bool_mask]
        st.session_state.filtered_df = filtered_df

    filtered_df = st.session_state.filtered_df
    st.write(f"### Showing {len(filtered_df)} cows")
    st.dataframe(filtered_df)

    csv_download = filtered_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Selected Cows as CSV",
        data=csv_download,
        file_name="selected_cows.csv",
        mime="text/csv"
    )

    # -------- Interactive Plots with numeric bins for Color only --------
    st.write("### 📊 Interactive Plots")
    plot_df = filtered_df.copy()

    # Fill missing values for categoricals
    for col in categorical_cols:
        plot_df[col] = plot_df[col].fillna("Missing").astype(str)

    # Prepare numeric bins for coloring safely
    num_bins = 3
    binned_cols = {}
    for col in numeric_cols:
        try:
            if plot_df[col].dropna().nunique() > 1:
                binned_col_name = f"{col}_class"
                plot_df[binned_col_name] = pd.cut(
                    plot_df[col],
                    bins=num_bins,
                    labels=[f"{col} Class {i+1}" for i in range(num_bins)],
                    duplicates='drop'
                )
                binned_cols[col] = binned_col_name
        except Exception as e:
            print(f"Skipping {col} for binning: {e}")

    color_options = [None] + categorical_cols + list(binned_cols.values())

    plot_type = st.selectbox(
        "Select plot type",
        ["Scatter", "Line", "Histogram", "Boxplot", "Bar (categorical vs numeric)", "Boxplot (categorical vs numeric)"]
    )

    if plot_type in ["Scatter", "Line"] and len(numeric_cols) >= 2:
        x_col = st.selectbox("X-axis variable", numeric_cols, key="xcol")
        y_col = st.selectbox("Y-axis variable", numeric_cols, key="ycol")
        color_col = st.selectbox("Color by (optional)", color_options, key="color1")
        fig = px.scatter(plot_df, x=x_col, y=y_col, color=color_col) if plot_type=="Scatter" else px.line(plot_df, x=x_col, y=y_col, color=color_col)
        st.plotly_chart(fig, use_container_width=True)

    elif plot_type=="Histogram" and numeric_cols:
        col = st.selectbox("Select variable", numeric_cols, key="histcol")
        color_col = st.selectbox("Color by (optional)", color_options, key="color2")
        fig = px.histogram(plot_df, x=col, color=color_col, nbins=20, barmode="overlay")
        st.plotly_chart(fig, use_container_width=True)

    elif plot_type=="Boxplot" and numeric_cols:
        col = st.selectbox("Select variable", numeric_cols, key="boxcol")
        color_col = st.selectbox("Group by (optional)", color_options, key="color3")
        fig = px.box(plot_df, y=col, color=color_col)
        st.plotly_chart(fig, use_container_width=True)

    elif plot_type=="Bar (categorical vs numeric)" and categorical_cols and numeric_cols:
        cat_col = st.selectbox("Select categorical variable", categorical_cols, key="barcat")
        num_col = st.selectbox("Select numeric variable", numeric_cols, key="barnum")
        color_col = st.selectbox("Color by (optional)", color_options, key="color4")
        fig = px.bar(plot_df, x=cat_col, y=num_col, color=color_col, barmode="group", text_auto=".2f")
        st.plotly_chart(fig, use_container_width=True)

    elif plot_type=="Boxplot (categorical vs numeric)" and categorical_cols and numeric_cols:
        cat_col = st.selectbox("Select categorical variable", categorical_cols, key="boxcat")
        num_col = st.selectbox("Select numeric variable", numeric_cols, key="boxnum")
        color_col = st.selectbox("Color by (optional)", color_options, key="color5")
        fig = px.box(plot_df, x=cat_col, y=num_col, color=color_col)
        st.plotly_chart(fig, use_container_width=True)
