# Data Processing Pipeline

Reference guide for cleaning, transforming, and analyzing extracted data. Follow this pipeline systematically after any data extraction operation.

---

## When to Use This Pipeline

Apply the full processing pipeline when:

- **After extraction**: Raw scraped data contains noise, encoding issues, or inconsistent formats
- **Data needs cleaning**: Missing values, duplicates, malformed entries, or inconsistent formatting detected
- **Merge multiple sources**: Combining data from different sources with different schemas or conventions
- **Need analysis**: Stakeholders require insights, statistics, or visualizations from the data
- **Quality assurance**: Data must meet quality standards before delivery or downstream use
- **Schema standardization**: Existing data must conform to a target schema

**Prerequisite**: Run Stage 1 (Raw Data Audit) before proceeding. If no issues found, document and skip to output.

---

## Pipeline Stages

### Stage 1: Raw Data Audit

Assess data quality before any modifications. Document findings for the quality report.

```python
import pandas as pd
import numpy as np

def audit_raw_data(df, source_name="source"):
    """Comprehensive data audit returning quality metrics."""
    audit = {
        "source": source_name,
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "column_types": df.dtypes.astype(str).to_dict(),
        "missing_values": {},
        "missing_pct": {},
        "duplicate_rows": df.duplicated().sum(),
        "duplicate_pct": round(df.duplicated().sum() / len(df) * 100, 2)
    }
    
    # Missing value analysis
    for col in df.columns:
        missing = df[col].isna().sum()
        audit["missing_values"][col] = missing
        audit["missing_pct"][col] = round(missing / len(df) * 100, 2)
    
    # Sample inspection - first 10 rows
    print("=== FIRST 10 ROWS ===")
    print(df.head(10).to_string())
    
    # Random sample inspection
    print("\n=== RANDOM 10 ROWS ===")
    print(df.sample(min(10, len(df))).to_string())
    
    # Encoding check for text columns
    for col in df.select_dtypes(include=['object']).columns:
        try:
            df[col].astype(str).encode('utf-8')
        except UnicodeEncodeError as e:
            print(f"Encoding issue in column '{col}': {e}")
    
    return audit
```

**Audit checklist**:
- [ ] Row and column counts documented
- [ ] Data types identified per column
- [ ] Missing values counted and percentages calculated
- [ ] Duplicate rows detected and counted
- [ ] First 10 rows inspected for obvious issues
- [ ] Random 10 rows inspected for edge cases
- [ ] Text encoding validated (UTF-8 standard)

---

### Stage 2: Cleaning

Apply cleaning operations in order. Log each transformation.

```python
def clean_data(df):
    """Multi-step data cleaning with logging."""
    cleaning_log = []
    
    # Step 1: Remove exact duplicates
    initial_rows = len(df)
    df = df.drop_duplicates()
    removed = initial_rows - len(df)
    if removed > 0:
        cleaning_log.append(f"Removed {removed} exact duplicate rows")
    
    # Step 2: Normalize whitespace and encoding
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].str.replace(r'\s+', ' ', regex=True)
        df[col] = df[col].apply(lambda x: x.encode('utf-8').decode('utf-8') if pd.notna(x) else x)
    cleaning_log.append("Normalized whitespace and ensured UTF-8 encoding")
    
    # Step 3: Standardize dates to ISO 8601
    date_columns = [col for col in df.columns if 'date' in col.lower() or 'time' in col.lower()]
    for col in date_columns:
        df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d')
    if date_columns:
        cleaning_log.append(f"Standardized {len(date_columns)} date columns to ISO 8601")
    
    # Step 4: Standardize numbers (remove formatting)
    for col in df.select_dtypes(include=['object']).columns:
        if df[col].str.contains(r'[\$,%]', na=False).any():
            df[col] = df[col].str.replace(r'[\$,]', '', regex=True)
            df[col] = df[col].str.replace(r'%', '', regex=True).astype(float) / 100
    
    # Step 5: Handle missing values (document strategy)
    # Options: drop, fill with mean/median/mode, forward fill, leave as null
    # Example: fill numeric with median, categorical with mode
    for col in df.columns:
        missing = df[col].isna().sum()
        if missing > 0:
            if df[col].dtype in ['int64', 'float64']:
                df[col] = df[col].fillna(df[col].median())
                cleaning_log.append(f"Filled {missing} missing values in '{col}' with median")
            else:
                df[col] = df[col].fillna(df[col].mode()[0] if len(df[col].mode()) > 0 else 'UNKNOWN')
                cleaning_log.append(f"Filled {missing} missing values in '{col}' with mode/UNKNOWN")
    
    # Step 6: Fix categorical typos and standardize values
    categorical_cols = df.select_dtypes(include=['object']).columns[:5]  # sample
    for col in categorical_cols:
        unique_vals = df[col].unique()
        if len(unique_vals) <= 20:  # Likely categorical
            df[col] = df[col].str.lower().str.strip()
            cleaning_log.append(f"Standardized categorical values in '{col}'")
    
    # Step 7: Validate and fix URLs
    url_pattern = r'https?://[^\s]+'
    for col in df.columns:
        if 'url' in col.lower() and df[col].dtype == 'object':
            invalid_urls = df[col][~df[col].str.match(url_pattern, na=False)]
            if len(invalid_urls) > 0:
                cleaning_log.append(f"Found {len(invalid_urls)} invalid URLs in '{col}'")
    
    # Step 8: Validate emails
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    for col in df.columns:
        if 'email' in col.lower() and df[col].dtype == 'object':
            df[col] = df[col].str.lower()
            invalid_emails = df[col][~df[col].str.match(email_pattern, na=False)]
            if len(invalid_emails) > 0:
                cleaning_log.append(f"Found {len(invalid_emails)} invalid emails in '{col}'")
    
    return df, cleaning_log
```

**Cleaning operations checklist**:
- [ ] Exact duplicates removed
- [ ] Whitespace normalized (trim, collapse internal spaces)
- [ ] Encoding standardized to UTF-8
- [ ] Dates converted to ISO 8601 (YYYY-MM-DD)
- [ ] Number formatting removed ($, commas, % converted)
- [ ] Missing values handled with documented strategy
- [ ] Categorical typos fixed (lowercase, trim)
- [ ] Text fields trimmed
- [ ] URLs validated
- [ ] Emails validated and lowercased

---

### Stage 3: Transformation

Derive new features and reshape data as needed.

```python
def transform_data(df):
    """Data transformation operations."""
    transformations = []
    
    # Type casting
    numeric_cols = ['id', 'count', 'quantity', 'amount', 'price', 'total']
    for col in df.columns:
        if any(term in col.lower() for term in numeric_cols):
            df[col] = pd.to_numeric(df[col], errors='coerce')
            transformations.append(f"Cast '{col}' to numeric")
    
    # Derive new fields
    if 'date' in [c.lower() for c in df.columns]:
        date_cols = [c for c in df.columns if 'date' in c.lower()]
        for col in date_cols:
            df[f'{col}_year'] = pd.to_datetime(df[col], errors='coerce').dt.year
            df[f'{col}_month'] = pd.to_datetime(df[col], errors='coerce').dt.month
            df[f'{col}_quarter'] = pd.to_datetime(df[col], errors='coerce').dt.quarter
            transformations.append(f"Derived year/month/quarter from '{col}'")
    
    # Merge/join by key
    # Example: df = pd.merge(df1, df2, on='id', how='left')
    
    # Reshape operations
    # Pivot: df.pivot(index='date', columns='category', values='value')
    # Unpivot: pd.melt(df, id_vars=['id'], value_vars=[...])
    
    # Categorize/bin numerical values
    if 'age' in df.columns:
        df['age_group'] = pd.cut(df['age'], bins=[0, 17, 35, 55, 100], 
                                  labels=['minor', 'young_adult', 'middle_aged', 'senior'])
        transformations.append("Created age_group bins")
    
    if 'income' in df.columns or 'salary' in df.columns:
        inc_col = 'income' if 'income' in df.columns else 'salary'
        df['income_tier'] = pd.qcut(df[inc_col].dropna(), q=4, 
                                     labels=['Q1_low', 'Q2', 'Q3', 'Q4_high'])
        transformations.append("Created income_tier quartiles")
    
    # Normalize/standardize numerical features
    from sklearn.preprocessing import StandardScaler
    numeric_features = df.select_dtypes(include=['int64', 'float64']).columns
    scaler = StandardScaler()
    # df[['normalized_col']] = scaler.fit_transform(df[['original_col']])
    
    return df, transformations
```

**Transformation checklist**:
- [ ] Type casting applied (strings to numeric, dates parsed)
- [ ] New fields derived (year from date, age groups, etc.)
- [ ] Merge/join operations completed with documented keys
- [ ] Reshape operations (pivot/unpivot) completed if needed
- [ ] Categorical bins created (quartiles, ranges)
- [ ] Numerical normalization applied if required for analysis

---

### Stage 4: Validation

Verify data quality after cleaning and transformation.

```python
def validate_data(df, expected_schema=None):
    """Comprehensive data validation."""
    validation_results = []
    
    # Schema validation
    if expected_schema:
        for field, dtype in expected_schema.items():
            if field in df.columns:
                if df[field].dtype != dtype:
                    validation_results.append({
                        "check": f"dtype_{field}",
                        "status": "FAIL",
                        "expected": str(dtype),
                        "actual": str(df[field].dtype)
                    })
                else:
                    validation_results.append({
                        "check": f"dtype_{field}",
                        "status": "PASS",
                        "expected": str(dtype),
                        "actual": str(df[field].dtype)
                    })
    
    # Range validation
    if 'age' in df.columns:
        invalid_age = df[(df['age'] < 0) | (df['age'] > 150)]
        validation_results.append({
            "check": "age_range",
            "status": "FAIL" if len(invalid_age) > 0 else "PASS",
            "invalid_count": len(invalid_age)
        })
    
    # Outlier detection - IQR method
    numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns
    for col in numeric_cols:
        Q1 = df[col].quantile(0.25)
        Q3 = df[col].quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        outliers = df[(df[col] < lower_bound) | (df[col] > upper_bound)]
        if len(outliers) > 0:
            validation_results.append({
                "check": f"outlier_iqr_{col}",
                "status": "WARN",
                "outlier_count": len(outliers),
                "pct": round(len(outliers) / len(df) * 100, 2)
            })
    
    # Outlier detection - Z-score method
    from scipy import stats
    for col in numeric_cols[:5]:  # Limit to 5 columns for performance
        z_scores = np.abs(stats.zscore(df[col].dropna()))
        outliers_z = (z_scores > 3).sum()
        if outliers_z > 0:
            validation_results.append({
                "check": f"outlier_zscore_{col}",
                "status": "INFO",
                "outliers": outliers_z
            })
    
    # Referential integrity (if foreign keys exist)
    # Example: ensure all user_ids in orders exist in users table
    
    # Business rule validation
    if 'start_date' in df.columns and 'end_date' in df.columns:
        invalid_dates = df[pd.to_datetime(df['end_date']) < pd.to_datetime(df['start_date'])]
        validation_results.append({
            "check": "date_logic",
            "status": "FAIL" if len(invalid_dates) > 0 else "PASS",
            "invalid_count": len(invalid_dates)
        })
    
    return validation_results

# Cross-source consistency check
def check_cross_source_consistency(df_list, key_column):
    """Verify consistency across multiple data sources."""
    results = []
    for i, df in enumerate(df_list):
        for j, other_df in enumerate(df_list[i+1:], i+1):
            df_keys = set(df[key_column].dropna())
            other_keys = set(other_df[key_column].dropna())
            in_both = df_keys & other_keys
            only_first = df_keys - other_keys
            only_second = other_keys - df_keys
            results.append({
                "comparison": f"df{i} vs df{j}",
                "shared_keys": len(in_both),
                "only_in_first": len(only_first),
                "only_in_second": len(only_second)
            })
    return results
```

**Validation checklist**:
- [ ] Schema validation: types and ranges match expectations
- [ ] Cross-source consistency verified
- [ ] Outliers detected (IQR and z-score methods)
- [ ] Referential integrity validated
- [ ] Business rules checked (date logic, value constraints)
- [ ] Sample spot-check against source data

---

### Stage 5: Analysis (When Requested)

Generate insights from cleaned data.

```python
def analyze_data(df, analysis_types=None):
    """Generate requested analyses."""
    if analysis_types is None:
        analysis_types = ['descriptive', 'frequency', 'correlation']
    
    results = {}
    
    # Descriptive statistics
    if 'descriptive' in analysis_types:
        results['descriptive_stats'] = {
            'numeric': df.describe().to_dict(),
            'missing_summary': {
                'total': df.isna().sum().sum(),
                'by_column': df.isna().sum().to_dict()
            }
        }
        
        # Calculate additional metrics
        for col in df.select_dtypes(include=['int64', 'float64']).columns:
            results['descriptive_stats'][col] = {
                'mean': round(df[col].mean(), 2),
                'median': round(df[col].median(), 2),
                'std': round(df[col].std(), 2),
                'q1': round(df[col].quantile(0.25), 2),
                'q3': round(df[col].quantile(0.75), 2),
                'iqr': round(df[col].quantile(0.75) - df[col].quantile(0.25), 2)
            }
    
    # Frequency tables for categorical
    if 'frequency' in analysis_types:
        results['frequency_tables'] = {}
        for col in df.select_dtypes(include=['object', 'category']).columns:
            if df[col].nunique() <= 50:  # Only for reasonable cardinality
                results['frequency_tables'][col] = df[col].value_counts().head(20).to_dict()
    
    # Correlation matrix
    if 'correlation' in analysis_types:
        numeric_df = df.select_dtypes(include=['int64', 'float64'])
        if len(numeric_df.columns) > 1:
            results['correlation_matrix'] = numeric_df.corr().to_dict()
    
    # Time series trends
    if 'time_series' in analysis_types:
        date_cols = [c for c in df.columns if 'date' in c.lower()]
        for col in date_cols:
            df[col] = pd.to_datetime(df[col], errors='coerce')
            df_sorted = df.sort_values(col)
            # Calculate trends (monthly counts, growth rates)
            results[f'time_series_{col}'] = {
                'start_date': str(df_sorted[col].min()),
                'end_date': str(df_sorted[col].max()),
                'span_days': (df_sorted[col].max() - df_sorted[col].min()).days,
                'record_count': len(df)
            }
    
    # Group comparisons
    if 'group_comparison' in analysis_types and 'category' in df.columns:
        results['group_comparison'] = df.groupby('category').agg({
            col: ['mean', 'median', 'count'] 
            for col in df.select_dtypes(include=['int64', 'float64']).columns
        }).to_dict()
    
    # Text analysis
    if 'text_analysis' in analysis_types:
        text_cols = df.select_dtypes(include=['object']).columns[:3]
        for col in text_cols:
            all_text = ' '.join(df[col].dropna().astype(str))
            words = all_text.lower().split()
            word_freq = pd.Series(words).value_counts().head(20).to_dict()
            
            # N-grams
            from collections import Counter
            bigrams = [' '.join(words[i:i+2]) for i in range(len(words)-1)]
            trigrams = [' '.join(words[i:i+3]) for i in range(len(words)-2)]
            results[f'text_analysis_{col}'] = {
                'word_frequency': word_freq,
                'top_bigrams': Counter(bigrams).most_common(10),
                'top_trigrams': Counter(trigrams).most_common(10)
            }
    
    return results
```

**Analysis checklist**:
- [ ] Descriptive statistics (mean, median, std, quartiles)
- [ ] Frequency tables for categorical variables
- [ ] Correlation matrix for numeric variables
- [ ] Time series trends and patterns
- [ ] Group comparisons and aggregations
- [ ] Text analysis (word frequency, n-grams)

---

### Stage 6: Output

Generate all deliverable files.

```python
def generate_outputs(df, audit, cleaning_log, validation_results, analysis_results, 
                     output_dir="output/"):
    """Generate all output files."""
    import json
    import os
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Clean dataset - multiple formats
    df.to_csv(f"{output_dir}clean_data.csv", index=False, encoding='utf-8')
    df.to_json(f"{output_dir}clean_data.json", orient='records', indent=2)
    # df.to_parquet(f"{output_dir}clean_data.parquet")  # Requires pyarrow
    
    # 2. Data dictionary
    data_dict = []
    for col in df.columns:
        entry = {
            "Field": col,
            "Type": str(df[col].dtype),
            "Non_Null_Count": int(df[col].notna().sum()),
            "Null_Count": int(df[col].isna().sum()),
            "Unique_Values": int(df[col].nunique()),
            "Sample": str(df[col].dropna().iloc[0]) if len(df[col].dropna()) > 0 else ""
        }
        data_dict.append(entry)
    
    # 3. Quality report
    quality_report = {
        "summary": {
            "initial_rows": audit.get("total_rows", 0),
            "final_rows": len(df),
            "rows_removed": audit.get("total_rows", 0) - len(df),
            "duplicates_removed": audit.get("duplicate_rows", 0)
        },
        "cleaning_log": cleaning_log,
        "validation_results": validation_results,
        "issues_identified": [v for v in validation_results if v.get("status") in ["FAIL", "WARN"]]
    }
    
    # Save quality report
    with open(f"{output_dir}quality_report.json", 'w') as f:
        json.dump(quality_report, f, indent=2, default=str)
    
    # 4. Analysis summary
    if analysis_results:
        with open(f"{output_dir}analysis_summary.json", 'w') as f:
            json.dump(analysis_results, f, indent=2, default=str)
    
    print(f"Outputs generated in {output_dir}")
    return quality_report
```

**Output checklist**:
- [ ] Clean dataset saved (CSV, JSON, Parquet as needed)
- [ ] Data dictionary generated
- [ ] Cleaning log documented
- [ ] Quality report generated
- [ ] Analysis summary produced (if analysis requested)
- [ ] Visualization references noted

---

## Data Dictionary Template

Create `data_dictionary.md` with this structure:

```markdown
# Data Dictionary

**Dataset**: [Dataset Name]  
**Source**: [Original Source]  
**Generated**: [Date]  
**Total Records**: [Count]  

| Field | Original Name | Type | Description | Example | Source | Cleaning Notes | Missingness |
|-------|---------------|------|-------------|---------|--------|----------------|-------------|
| id | record_id | string | Unique identifier | abc123 | Original | Extracted from URL | 0% |
| created_date | date_created | date | Record creation date | 2024-01-15 | Original | Converted from MM/DD/YYYY | 2% |
| amount | monetary_value | float | Transaction amount USD | 149.99 | Calculated | Removed $ formatting | 0% |
| category | classification | string | Product category | electronics | Original | Lowercased, standardized typos | 5% |
| status | record_status | string | Processing status | active | Original | Mapped 'in progress' to 'active' | 0% |
| email | contact_email | string | User email address | user@example.com | Original | Validated format | 1% |
| url | source_url | string | Source webpage | https://... | Original | Validated, encoded | 0% |
```

---

## Quality Report Template

Create `quality_report.md` with this structure:

```markdown
# Data Quality Report

**Report Date**: [YYYY-MM-DD]  
**Dataset**: [Name]  
**Processing Pipeline Version**: [v1.0]

---

## Summary Statistics

| Metric | Value |
|--------|-------|
| Total Rows (Raw) | 10,000 |
| Total Rows (Clean) | 9,850 |
| Total Columns | 15 |
| Duplicate Rows Removed | 150 |
| Records with Issues | 200 |

---

## Data Quality Metrics

| Metric | Raw Data | Clean Data |
|--------|----------|------------|
| Missing Values | 500 (0.5%) | 0 (0%) |
| Invalid Dates | 25 | 0 |
| Invalid Emails | 10 | 0 |
| Outliers Detected | 45 | 0 |

---

## Cleaning Operations Applied

1. **Duplicate Removal**: Removed 150 exact duplicate rows based on id field
2. **Date Standardization**: Converted 3 date columns from MM/DD/YYYY to ISO 8601
3. **Missing Value Handling**: Filled 350 numeric missing values with median; 150 categorical with mode
4. **Text Normalization**: Trimmed whitespace, standardized to lowercase for categorical fields
5. **Email Validation**: Flagged 10 invalid email formats for review

---

## Validation Results

| Check | Status | Details |
|-------|--------|---------|
| Schema Validation | ✅ PASS | All fields match expected types |
| Date Range | ⚠️ WARN | 15 dates in future (flagged) |
| Required Fields | ✅ PASS | All required fields present |
| Referential Integrity | ✅ PASS | Foreign keys validated |
| Business Rules | ✅ PASS | All business rules satisfied |

---

## Known Issues

| Issue | Impact | Resolution |
|-------|--------|------------|
| 10 records with future dates | Low | Flagged for manual review |
| 3 URL redirects detected | Low | Updated to final destination |
| 2% missing email addresses | Medium | Filled with placeholder |

---

## Recommendations

1. Implement real-time validation at data entry point
2. Add automated duplicate detection workflow
3. Schedule weekly data quality checks
```

---

## Tools Reference

### Python Libraries

```python
# Core data processing
import pandas as pd
import numpy as np

# Statistical analysis
from scipy import stats
from scipy.stats import zscore, iqr

# Advanced processing
# pip install pandas scikit-learn scipy openpyxl xlrd pyarrow
```

### Shell Commands

```bash
# csvkit - command-line CSV processing
csvstat data.csv                    # Summary statistics
csvclean -n data.csv               # Find errors
csvsort -c 3 data.csv              # Sort by column 3
csvjoin data1.csv data2.csv        # Merge CSVs
csvsql --query "SELECT *" data.csv # SQL queries

# jq - JSON processing
jq '.[] | select(.id > 100)' data.json
jq 'group_by(.category)' data.json
jq 'map({key: .name, value: .count})' data.json

# miller - multi-format data processing
mlr --csv stats1 -a mean,sum data.csv
mlr --csv cut -f id,name,value data.csv
mlr --csv sort -f category -n value data.csv
```

### Data Cleaning Script Template

```python
#!/usr/bin/env python3
"""
data_clean.py - Standardized data cleaning pipeline
Usage: python data_clean.py <input_file> <output_dir>
"""

import sys
import pandas as pd
import json
from pathlib import Path

def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else "data/raw.csv"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "data/clean/"
    
    # Load data
    df = pd.read_csv(input_file)
    
    # Run pipeline stages
    audit = audit_raw_data(df, input_file)
    df_clean, cleaning_log = clean_data(df)
    df_clean, transformations = transform_data(df_clean)
    validation = validate_data(df_clean)
    
    # Generate outputs
    generate_outputs(df_clean, audit, cleaning_log, validation, {}, output_dir)
    
    print(f"✅ Processing complete: {audit['total_rows']} → {len(df_clean)} rows")

if __name__ == "__main__":
    main()
```

---

## Quick Reference Checklist

Before completing any data processing task:

- [ ] Stage 1: Raw data audited and documented
- [ ] Stage 2: All cleaning operations logged
- [ ] Stage 3: Transformations justified and documented
- [ ] Stage 4: Validation results recorded
- [ ] Stage 5: Analysis completed (if requested)
- [ ] Stage 6: All output files generated
- [ ] Data dictionary created
- [ ] Quality report generated
- [ ] All findings summarized
