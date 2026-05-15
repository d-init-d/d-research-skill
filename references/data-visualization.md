# Data Visualization Guide

## When to Use

Use visualizations when:

- **Report needs charts**: Stakeholder presentations or executive summaries benefit from visual data summaries
- **Dataset summary needs visual**: Quick overview of distributions, patterns, or key metrics
- **Comparison/trend analysis**: Comparing categories, showing changes over time, or highlighting relationships
- **User requests dashboard**: Interactive or static dashboards for ongoing monitoring

Default to tables for small datasets (<10 rows), but use charts for patterns across larger data.

---

## Chart Type Selection

| Data Pattern | Chart Type | Tool |
|-------------|------------|------|
| Distribution | Histogram / Box plot | matplotlib / plotly |
| Comparison | Bar chart / Grouped bar | matplotlib / plotly |
| Trend over time | Line chart / Area chart | matplotlib / plotly |
| Composition | Pie chart / Stacked bar | matplotlib / plotly |
| Relationship | Scatter plot / Heatmap | matplotlib / seaborn |
| Ranking | Horizontal bar / Lollipop | matplotlib / plotly |
| Geographic | Choropleth / Point map | plotly / folium |
| Network | Node-link graph | networkx + matplotlib |
| Text | Word cloud / Frequency bar | wordcloud |

**Quick decision guide:**
- **Categories → Bar chart**
- **Time → Line chart**
- **Parts of whole → Pie or stacked bar**
- **Distribution → Histogram or box plot**
- **Correlation → Scatter plot**

---

## Static Charts (matplotlib)

For PDF reports, academic papers, or simple exports.

```python
import matplotlib.pyplot as plt
import pandas as pd

# Create a simple bar chart
df = pd.DataFrame({'Category': ['A', 'B', 'C', 'D'],
                   'Value': [45, 32, 78, 56]})

plt.figure(figsize=(8, 5))
plt.bar(df['Category'], df['Value'], color='#3498db')
plt.title('Category Comparison', fontsize=14, fontweight='bold')
plt.xlabel('Category')
plt.ylabel('Value')
plt.savefig('chart.png', dpi=300, bbox_inches='tight')
plt.close()
```

**Output formats:** PNG (screenshots), SVG (publications), PDF (print)

```python
# Save in multiple formats
plt.savefig('chart.png', dpi=300)
plt.savefig('chart.svg')
plt.savefig('chart.pdf')
```

---

## Interactive Charts (plotly)

For HTML reports, dashboards, or exploratory analysis.

```python
import plotly.express as px

# Create interactive bar chart
df = px.data.iris()
fig = px.bar(df, x='species', y='sepal_width', 
             title='Sepal Width by Species',
             color='species')

# Save as interactive HTML
fig.write_html('interactive_chart.html')

# Or display inline
fig.show()
```

```python
# Line chart for time series
fig = px.line(df, x='date', y='value', 
              title='Trends Over Time',
              labels={'date': 'Date', 'value': 'Value'})

fig.update_layout(template='plotly_white')
fig.write_html('trend_chart.html')
```

**Output formats:** HTML (interactive), PNG (static from plotly)

```python
# Export plotly chart as static image
fig.write_image('chart.png', width=800, height=500)
```

---

## Report Embedding

**Markdown (for .md reports):**
```markdown
![Category Comparison](charts/sales_by_region.png)

*Source: Internal Sales Data, Q4 2024*
```

**HTML (for web reports):**
```html
<img src="chart.png" alt="Sales Chart" width="800">
<p><em>Source: Internal Sales Data, Q4 2024</em></p>
```

For plotly interactive charts in HTML:
```html
<div id="chart-container">
    <script src="plotly-latest.min.js"></script>
    <div id="chart" align="center"></div>
    <script>
        Plotly.d3.csv('data.csv', function(err, rows){
            // Load and display interactive chart
        });
    </script>
</div>
```

**LaTeX (for academic papers):**
```latex
\begin{figure}[htbp]
    \centering
    \includegraphics[width=0.8\textwidth]{chart.pdf}
    \caption{Sales Distribution by Region}
    \label{fig:sales}
\end{figure}
```

---

## Dashboard Template HTML

```html
<!DOCTYPE html>
<html>
<head>
    <title>Data Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { text-align: center; margin-bottom: 30px; }
        .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: #f5f5f5; padding: 20px; border-radius: 8px; text-align: center; }
        .stat-value { font-size: 2em; font-weight: bold; color: #2c3e50; }
        .stat-label { color: #7f8c8d; margin-top: 5px; }
        .charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; }
        .data-table { margin-top: 30px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #2c3e50; color: white; }
        .footer { margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #7f8c8d; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Data Dashboard</h1>
        <p>Generated: <span id="timestamp"></span></p>
    </div>

    <div class="stats-grid">
        <div class="stat-card"><div class="stat-value">1,234</div><div class="stat-label">Total Records</div></div>
        <div class="stat-card"><div class="stat-value">$45.2K</div><div class="stat-label">Total Value</div></div>
        <div class="stat-card"><div class="stat-value">87%</div><div class="stat-label">Completion Rate</div></div>
        <div class="stat-card"><div class="stat-value">12</div><div class="stat-label">Categories</div></div>
    </div>

    <div class="charts-row">
        <div id="chart1"></div>
        <div id="chart2"></div>
    </div>

    <div class="data-table">
        <h3>Data Summary</h3>
        <table>
            <tr><th>Category</th><th>Count</th><th>Percentage</th></tr>
            <tr><td>Category A</td><td>450</td><td>36.5%</td></tr>
            <tr><td>Category B</td><td>380</td><td>30.8%</td></tr>
            <tr><td>Category C</td><td>404</td><td>32.7%</td></tr>
        </table>
    </div>

    <div class="footer">
        <p>Source: Sample Data | Date Range: 2024-01-01 to 2024-12-31</p>
    </div>

    <script>
        document.getElementById('timestamp').textContent = new Date().toLocaleString();
        // Add Plotly chart code here
        var trace1 = {x: ['A', 'B', 'C'], y: [45, 32, 78], type: 'bar', name: 'Series 1'};
        Plotly.newPlot('chart1', [trace1], {title: 'Chart 1 Title'});
    </script>
</body>
</html>
```

---

## Guidelines

**Always include:**
- Axis labels and units
- Chart title
- Data source attribution
- Date range or timestamp

**Design principles:**
- Use colorblind-friendly palettes (Okabe-Ito, viridis, ortab10)
- Keep charts simple: one key insight per chart
- Use consistent colors across related charts
- Prefer horizontal bar charts for long category names

**Formatting:**
- Export as SVG for publications and presentations
- Use PNG (300+ DPI) for reports and documents
- Use HTML interactive for dashboards and web reports

**Common mistakes to avoid:**
- 3D charts (hard to read)
- Truncated axes without indication
- Too many categories (>7 = group or filter)
- Missing legends for multi-series charts
