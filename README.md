# 📊 IB Comps Agent: Automated SEC 10-K Benchmarking

An AI-powered financial agent that automates **Comparable Company Analysis (Comps)** by extracting real-time financial data from SEC EDGAR filings. Built for MBA-level financial analysis and investment research.

## 🚀 Key Features
- **Automated Extraction**: Uses `edgartools` to pull the latest 10-K and 20-F filings directly from the SEC.
- **AI-Powered Analysis**: Leverages **Gemini 2.0 Flash** to parse messy financial tables into structured data (Revenue, Net Income, EBITDA).
- **Valuation Multiples**: Integrates `yfinance` to calculate real-time **P/E Ratios** and **EV/Revenue** benchmarks.
- **Interactive Dashboard**: A Streamlit-based UI for dynamic peer group selection and data visualization.

## 🛠️ Tech Stack
- **Language**: Python 3.10+
- **AI Model**: Google Gemini 2.0 Flash
- **Data Sources**: SEC EDGAR (via `edgartools`), Yahoo Finance (`yfinance`)
- **Frontend**: Streamlit
- **Data Science**: Pandas, NumPy

## 📦 Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone [https://github.com/Yeshprabhu03/ai-10k-comps-agent.git](https://github.com/Yeshprabhu03/ai-10k-comps-agent.git)
   cd ai-10k-comps-agent
