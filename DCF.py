from flask import Flask, render_template, request
import json
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.request import urlopen

app = Flask(__name__)

# API and HEADERS settings
api_key = os.environ.get("API_KEY")
if not api_key:
    raise ValueError("API_KEY not set in environment variables")
headers = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/94.0.4606.61 Safari/537.36'
    )
}

def get_stock_price(stock_code):
    url = f"https://financialmodelingprep.com/api/v3/profile/{stock_code.upper()}?apikey={api_key}"
    response = requests.get(url)
    stock_data = response.json()
    if not stock_data:
        raise ValueError("No data found (get_stock_price)")
    price = stock_data[0].get('price', 0)
    companyName = stock_data[0].get('companyName', "")
    industry = stock_data[0].get('industry', "")
    return price, companyName, industry

def get_ttm_free_cash_flow(stock_code):
    url = f"https://financialmodelingprep.com/api/v3/cash-flow-statement/{stock_code.upper()}?period=quarter&limit=4&apikey={api_key}"
    response = requests.get(url)
    stock_data = response.json()
    if len(stock_data) < 4:
        raise ValueError("Insufficient data to calculate TTM Free Cash Flow")
    free_cash_flows = [quarter['freeCashFlow'] for quarter in stock_data[:4]]
    ttm_free_cash_flow = round(sum(free_cash_flows) / 1_000_000, 2)
    most_recent_date = stock_data[0]['date']
    most_recent_year = int(most_recent_date.split("-")[0])
    currency = stock_data[0]['reportedCurrency']
    return ttm_free_cash_flow, most_recent_year, currency

def get_ttm_revenue_shareoutstanding(stock_code):
    url = f"https://financialmodelingprep.com/api/v3/income-statement/{stock_code.upper()}?period=quarter&limit=4&apikey={api_key}"
    response = requests.get(url)
    stock_data = response.json()
    if len(stock_data) < 4:
        raise ValueError("Insufficient data to calculate TTM Revenue")
    revenues = [quarter['revenue'] for quarter in stock_data[:4]]
    ttm_revenue = round(sum(revenues) / 1_000_000, 2)
    most_recent_date = stock_data[0]['date']
    most_recent_year = int(most_recent_date.split("-")[0])
    shares_outstanding = round(stock_data[0].get('weightedAverageShsOutDil', 0) / 1_000_000, 2)
    return ttm_revenue, most_recent_year, shares_outstanding

def get_wacc_netdabt(stock_code):
    url = f"https://financialmodelingprep.com/api/v4/advanced_discounted_cash_flow?symbol={stock_code.upper()}&apikey={api_key}"
    response = urlopen(url)
    data_str = response.read().decode("utf-8")
    data_json = json.loads(data_str)
    data_df = pd.json_normalize(data_json).T
    wacc_value = data_df.loc["wacc"].iloc[0] if "wacc" in data_df.index else 0.0
    wacc = round(wacc_value, 2) if isinstance(wacc_value, float) else 0.0
    net_debt = data_df.loc["netDebt"].iloc[0] if "netDebt" in data_df.index else 0
    if isinstance(net_debt, (int, float)):
        net_debt = round(net_debt / 1_000_000, 2)
    else:
        net_debt = 0
    return wacc, net_debt

def growth_rate(stock_code):
    url = f"https://finance.yahoo.com/quote/{stock_code}/analysis"
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")
    items = soup.find_all(class_="Ta(end) Py(10px)")
    if len(items) < 17:
        return 0.0
    grown_text = items[16].text
    if grown_text == 'N/A':
        return 0.0
    return float(grown_text.replace("%", ""))

def get_cash_equivalents_and_total_debt(stock_code):
    url = f"https://financialmodelingprep.com/api/v3/balance-sheet-statement/{stock_code.upper()}?period=quarter&limit=1&apikey={api_key}"
    response = requests.get(url)
    stock_data = response.json()
    if not stock_data:
        raise ValueError("No data found (get_cash_equivalents_and_total_debt)")
    cash_equivalents = stock_data[0].get('cashAndShortTermInvestments', 0)
    total_debt = stock_data[0].get('totalDebt', 0)
    cash_equivalents = round(cash_equivalents / 1_000_000, 2)
    total_debt = round(total_debt / 1_000_000, 2)
    return cash_equivalents, total_debt

@app.route('/', methods=["GET", "POST"])
def index():
    error = None
    stock = None
    results = {}
    
    if request.method == "POST":
        try:
            new_stock = request.form.get("stock", "AAPL").upper()
            prev_stock = request.form.get("prev_stock", "").upper()
            stock = new_stock
            
            # Fetch new stock data if the stock code has changed
            if new_stock != prev_stock:
                growth_rate_input = growth_rate(new_stock)
                f_growth_value = 2.5
                margin_of_safety = 100.0  # Default to 100% (no discount)
                price, companyName, industry = get_stock_price(new_stock)
                ttm_fcf, latest_year, currency = get_ttm_free_cash_flow(new_stock)
                ttm_revenue, _, share_outstanding = get_ttm_revenue_shareoutstanding(new_stock)
                wacc_default, net_debt = get_wacc_netdabt(new_stock)
                cash, total_debt_api = get_cash_equivalents_and_total_debt(new_stock)

                # Set custom WACC and FCF to the default values for the new stock
                user_wacc = wacc_default
                user_ttm_fcf = ttm_fcf
            else:
                # Use previously fetched data but update user inputs
                growth_rate_input = float(request.form.get("growth_rate_input") or growth_rate(new_stock))
                f_growth_value = float(request.form.get("f_growth") or "2.5")
                margin_of_safety = float(request.form.get("margin_of_safety") or "100.0")
                price, companyName, industry = get_stock_price(new_stock)
                ttm_fcf, latest_year, currency = get_ttm_free_cash_flow(new_stock)
                ttm_revenue, _, share_outstanding = get_ttm_revenue_shareoutstanding(new_stock)
                wacc_default, net_debt = get_wacc_netdabt(new_stock)
                cash, total_debt_api = get_cash_equivalents_and_total_debt(new_stock)

                # For existing stock, get custom values from form if they exist
                user_wacc = float(request.form.get("wacc", str(wacc_default)))
                user_ttm_fcf = float(request.form.get("ttm_fcf", str(ttm_fcf)))
            
            # FCF Yield calculation in percent
            fcf_yield = round((ttm_fcf / ttm_revenue) * 100, 2) if ttm_revenue != 0 else 0.0
            
            # DCF model calculations
            years = list(range(latest_year, latest_year + 11))
            fcf_list = [user_ttm_fcf]
            for i in range(1, 11):
                next_fcf = round(fcf_list[-1] * (1 + growth_rate_input / 100), 2)
                fcf_list.append(next_fcf)
            
            terminal_value = 0.0
            if (user_wacc / 100) != (f_growth_value / 100):
                terminal_value = (fcf_list[-1] * (1 + f_growth_value / 100)) / ((user_wacc / 100) - (f_growth_value / 100))
            
            discount_rate = user_wacc / 100
            pv_list = [round(fcf_list[i] / ((1 + discount_rate) ** i), 2) for i in range(len(fcf_list))]
            terminal_value_pv = terminal_value / ((1 + discount_rate) ** 10)
            
            # Enterprise Value (EV)
            ev_val = sum(pv_list[1:]) + terminal_value_pv
            equity_value = ev_val + cash - total_debt_api
            intrinsic_value = round(equity_value / share_outstanding, 2) if share_outstanding else 0
            adjusted_intrinsic_value = round(intrinsic_value * (margin_of_safety / 100), 2)
            
            # Prepare DCF table data
            dcf_table = []
            for i, yr in enumerate(years):
                dcf_table.append({
                    "year": yr,
                    "fcf": fcf_list[i],
                    "pv": pv_list[i]
                })
            
            results = {
                "price": price,
                "companyName": companyName,
                "industry": industry,
                "ttm_fcf": ttm_fcf,
                "latest_year": latest_year,
                "currency": currency,
                "ttm_revenue": ttm_revenue,
                "share_outstanding": share_outstanding,
                "wacc": wacc_default,
                "growth_rate": growth_rate(new_stock),
                "cash": cash,
                "total_debt": total_debt_api,
                "fcf_yield": fcf_yield,
                "dcf_table": dcf_table,
                "terminal_value": terminal_value,
                "terminal_value_pv": terminal_value_pv,
                "ev": ev_val,
                "equity_value": equity_value,
                "intrinsic_value": intrinsic_value,
                "adjusted_intrinsic_value": adjusted_intrinsic_value,
                "growth_rate_input": growth_rate_input,
                "f_growth": f_growth_value,
                "user_wacc": user_wacc,
                "user_ttm_fcf": user_ttm_fcf,
                "net_debt": net_debt,
                "margin_of_safety": margin_of_safety
            }
        except Exception as e:
            error = str(e)
    else:
        # Default to AAPL for GET requests
        stock = "AAPL"
        try:
            wacc_default, net_debt = get_wacc_netdabt(stock)
            default_growth_rate = growth_rate(stock)
            ttm_fcf, latest_year, currency = get_ttm_free_cash_flow(stock)
        except Exception as e:
            wacc_default = 0
            default_growth_rate = 10.0
            ttm_fcf, latest_year, currency = 0, 2023, "USD"
        results = {
            "growth_rate_input": 10.0,
            "f_growth": 2.5,
            "user_wacc": wacc_default,
            "user_ttm_fcf": ttm_fcf,
            "margin_of_safety": 100.0  # Default margin of safety
        }
        
    return render_template('index.html', stock=stock, error=error, results=results)

if __name__ == '__main__':
    app.run(debug=True)