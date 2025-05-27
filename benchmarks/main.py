import pandas as pd
from datetime import datetime
import re


# =============== НАСТРОЙКИ ===============
# CSV-файлы
INDEX_CSV   = 'IMOEX_TR.csv'   # TRADEDATE;CLOSE
FUND_CSV    = 'FUND_NAV.csv'   # Date;NAV
DEPO_CSV    = 'DEPOSIT.csv'    # Date;Rate (годовая %)
CPI_CSV     = 'CPI.csv'        # Date;CPI (к предыдущему месяцу, %)

# Номера колонок (считать с 0)
IDX_DATE, IDX_PRICE   = 0, 1
FUND_DATE, FUND_PRICE = 0, 1
DEPO_DATE, DEPO_RATE  = 0, 1
CPI_DATE,  CPI_RATE   = 0, 1

# Формат даты
DATE_FMT = '%d.%m.%Y'

# Диапазон анализа
START = '01.01.2010'
END   = '30.04.2025'

# Комиссия и проскальзывание (%)
COMM = 0.05 / 100
SLIP = 0.02 / 100
# =========================================


def parse_deposit_date(decade_str: str):
    m = re.match(r'(I{1,3})\.(\d{2})\.(\d{4})', decade_str.strip())
    if not m:
        return pd.NaT
    dec, mm, yyyy = m.groups()
    dd = {'I': 5, 'II': 15, 'III': 25}[dec]
    return datetime(int(yyyy), int(mm), dd)


def load_price_series(csv_path, date_col, price_col):
    df = pd.read_csv(csv_path, sep=';', decimal=',', engine='python',
                     on_bad_lines='skip', encoding='utf-8')
    dates  = pd.to_datetime(df.iloc[:, date_col], format=DATE_FMT,
                            errors='coerce')
    prices = pd.to_numeric(df.iloc[:, price_col], errors='coerce')
    ser = pd.Series(prices.values, index=dates).dropna().sort_index()
    return ser


def period_return(series, start, end, apply_costs=True):
    sub = series.loc[start:end]
    if len(sub) < 2:
        return None, None
    entry, exit_ = sub.iloc[0], sub.iloc[-1]
    gross = exit_ / entry - 1
    if apply_costs:
        net = gross - 2 * (COMM + SLIP)
    else:
        net = gross
    years = (sub.index[-1] - sub.index[0]).days / 365.25
    ann   = (1 + net) ** (1/years) - 1
    return net, ann


def safe_period_return(series, start, end, apply_costs=True, require_full=True):
    if series.empty:
        return None, None

    if require_full:
        start_dt = pd.to_datetime(start, format=DATE_FMT)
        end_dt = pd.to_datetime(end, format=DATE_FMT)
        if series.index.min() > start_dt or series.index.max() < end_dt:
            return None, None

    sub = series.loc[start:end]
    if sub.size < 2:
        return None, None

    return period_return(series, start, end, apply_costs)


# --- MCFTR и ПИФ ---
idx_price  = load_price_series(INDEX_CSV, IDX_DATE,  IDX_PRICE)
fund_price = load_price_series(FUND_CSV,  FUND_DATE, FUND_PRICE)

idx_cum,  idx_ann  = safe_period_return(idx_price,  START, END)
fund_cum, fund_ann = safe_period_return(fund_price, START, END)


# --- Депозит ---
dep_raw = pd.read_csv(DEPO_CSV, sep=';', decimal=',',
                      names=['Date', 'Rate'], header=0,
                      on_bad_lines='skip', encoding='utf-8')
dep_raw['Date'] = dep_raw['Date'].apply(parse_deposit_date)
dep_raw.dropna(inplace=True)

depo = pd.Series(dep_raw['Rate'].astype(float).values,
                 index=dep_raw['Date']).sort_index()

if depo.empty:
    depo_cum = depo_ann = None
else:
    daily_factor = (1 + depo / 100) ** (1/365.25)

    daily_factor = daily_factor.reindex(
        pd.date_range(daily_factor.index.min(),
                      daily_factor.index.max()),
        method='pad')

    depo_cum, depo_ann = safe_period_return(
        daily_factor.cumprod(), START, END, apply_costs=False)


# --- Инфляция ---
cpi_series = load_price_series(CPI_CSV, CPI_DATE, CPI_RATE)

if cpi_series.empty:
    cpi_cum = cpi_ann = None
else:
    cpi_factor = cpi_series / 100
    cpi_cum, cpi_ann = safe_period_return(
        cpi_factor.cumprod(), START, END, apply_costs=False)


# --- Вывод ---
print(f"\nПериод анализа: {START} — {END}")
print(f"Комиссия+проскальзывание моделируемые: {COMM*100:.3f}% / "
      f"{SLIP*100:.3f}% (на вход и выход)\n")

def pretty(name, cum, ann):
    if cum is None:
        print(f"{name:<20}: нет данных на всём интервале")
    else:
        print(f"{name:<20}: Накопл. {cum:>8.2%} | Среднегод. {ann:>7.2%}")


print("=== Buy&Hold бенчмарки ===")
pretty("MCFTR",          idx_cum,  idx_ann)
pretty("Индексный ПИФ",  fund_cum, fund_ann)
pretty("Депозит",        depo_cum, depo_ann)
pretty("Инфляция (CPI)", cpi_cum,  cpi_ann)