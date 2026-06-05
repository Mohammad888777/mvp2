import json
import pandas as pd
import numpy as np
import io
import os


# import matplotlib
# matplotlib.use('Agg')

# import matplotlib.pyplot as plt

import jdatetime

from openai import OpenAI
from typing import Dict, List, Any 

client = OpenAI(
    base_url=os.getenv('BASE_URL'),
    api_key=os.getenv('API_KEY'),
    timeout=60,  
    max_retries=2

)

ALLOWED_FIELDS = [
    'revenue',
    'quantity',
    'profit',
    'date',
    'customer',
    'product',
    'status',
    'unknown'
]


PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ENGLISH_DIGITS = "0123456789"


# convert fa number to en number
def fa_to_en(value):

    if value is None or pd.isna(value):
        return value

    value = str(value)

    for fa, en in zip(PERSIAN_DIGITS, ENGLISH_DIGITS):
        value = value.replace(fa, en)

    value = value.replace("٬", "")
    value = value.replace(",", "")

    return value.strip()



#date parser
def smart_parse_date(value):

    if value is None or pd.isna(value):
        return pd.NaT

    value = fa_to_en(value)

    # Gregorian
    try:
        return pd.to_datetime(value)
    except:
        pass

    # jalali
    try:

        if "/" in value:
            parts = value.split("/")
        elif "-" in value:
            parts = value.split("-")
        else:
            return pd.NaT

        if len(parts) != 3:
            return pd.NaT

        y, m, d = map(int, parts)

        jd = jdatetime.date(y, m, d)

        return pd.Timestamp(jd.togregorian())

    except:
        return pd.NaT




def clean_value(val):

    if pd.isna(val):
        return None

    if isinstance(val, pd.Timestamp):
        return str(val)

    if isinstance(val, (np.integer,)):
        return int(val)

    if isinstance(val, (np.floating,)):
        return float(val)

    if isinstance(val, np.ndarray):
        return val.tolist()

    try:
        json.dumps(val)
        return val

    except:
        return str(val)



#read excel or csv file

def read_excel_file(file_content: bytes, filename: str):

    if not filename.lower().endswith(('.xlsx', '.xls', '.csv')):
        raise ValueError(
            "فقط فایل‌های Excel یا CSV قابل قبول هستند."
        )

    try:

        if filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content))

        else:
            df = pd.read_excel(
                io.BytesIO(file_content),
                engine='openpyxl'
            )

    except Exception as e:
        raise ValueError(f"خطا در خواندن فایل: {e}")

    if df.empty:
        raise ValueError("فایل خالی است.")

    return df



# detect file columns with ai

def detect_columns_with_ai(columns: list, sample_rows: list):
    safe_rows = [
        {k: clean_value(v) for k, v in row.items()}
        for row in sample_rows[:3]  # فقط ۳ سطر کافی است
    ]

    prompt = f"""
                شما یک متخصص هوشمند نگاشت ستون‌های فروش هستید.

                ستون‌های موجود در فایل:
                {columns}

                نمونه داده (۳ سطر اول):
                {json.dumps(safe_rows, ensure_ascii=False, indent=2)}

                کار تو این است که **هر ستون** را به یکی از این دسته‌ها نگاشت کنی:
                {', '.join(ALLOWED_FIELDS)}

                قوانین مهم:
                - فقط خروجی JSON بده، هیچ متن اضافی ننویس.
                - فرمت دقیق خروجی باید به این شکل باشد:
                {{
                "نام ستون اول": "revenue",
                "نام ستون دوم": "date",
                "نام ستون سوم": "product",
                ...
                }}
                - اگر واقعاً هیچ تطابقی پیدا نکردی از "unknown" استفاده کن.
                - نام ستون‌ها را دقیقاً همان‌طور که هست بنویس (حساس به حروف کوچک و بزرگ).

                مثال خوب:
                {{
                "مبلغ فروش": "revenue",
                "تاریخ سفارش": "date",
                "نام مشتری": "customer",
                "تعداد": "quantity",
                "محصول": "product"
                }}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "تو یک دستیار بسیار دقیق و حرفه‌ای هستی که همیشه خروجی JSON معتبر و بدون هیچ توضیح اضافی می‌دهی."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,           # خیلی مهم برای ثبات
            response_format={"type": "json_object"}
        )

        suggested = json.loads(response.choices[0].message.content)
        sec_suggested = json.loads(response.choices[0].message.content)

        # اطمینان از اینکه همه ستون‌ها وجود دارند
        for col in columns:
            if col not in suggested or suggested[col] not in ALLOWED_FIELDS:
                suggested[col] = "unknown"

        return suggested,sec_suggested

    except Exception as e:
        print("AI Column Detection Error:", e)
       
        return {col: "unknown" for col in columns}




def detect_and_suggest_fix(
    df: pd.DataFrame,
    mapping: dict
):

    df = df.copy()

    issues = []

    important_targets = [
        'revenue',
        'profit',
        'quantity',
        'date',
        'customer',
        'product',
        'status'
    ]

    target_to_orig = {

        t: o

        for o, t in mapping.items()

        if t in important_targets
    }

    for target, original in target_to_orig.items():

        if original not in df.columns:
            continue

        series = df[original].copy()

   
        #empty string => none

        if series.dtype == object:

            series = series.replace(
                r'^\s*$',
                np.nan,
                regex=True
            )

        #numberic columns
    
        if target in [
            'revenue',
            'profit',
            'quantity'
        ]:

            series = series.apply(
                fa_to_en
            )

            series = pd.to_numeric(
                series,
                errors='coerce'
            )

            #column avg

            mean_value = series.mean()

            if pd.isna(mean_value):
                mean_value = 0

            mean_value = round(
                float(mean_value),
                2
            )

            # filling empty rows

            null_indexes = series[
                series.isna()
            ].index.tolist()

            for idx in null_indexes:

                series.at[idx] = mean_value

                df.at[idx, original] = mean_value

                issues.append({

                    'row': int(idx),

                    'column': original,

                    'target': target,

                    'suggested_value': mean_value
                })

            df[original] = series

        # date column
        elif target == 'date':

            def normalize_date(val):

                if pd.isna(val):
                    return np.nan

                original = str(val).strip()

                val = fa_to_en(original)

                #only year

                if str(val).isdigit():

                    year = int(val)

                    # shamsi
                    if year < 1700:

                        return f"{year}/01/01"

                    #miladi
                    else:

                        return f"{year}-01-01"

                # shamsi date

                if "/" in val:

                    parts = val.split("/")

                    if len(parts) == 3:

                        try:

                            y = int(parts[0])

                            if y < 1700:

                                m = int(parts[1])
                                d = int(parts[2])

                                return f"{y:04d}/{m:02d}/{d:02d}"

                        except:
                            pass

                # miladi date

                try:

                    dt = pd.to_datetime(
                        val,
                        errors='coerce'
                    )

                    if pd.notna(dt):

                        return dt.strftime(
                            "%Y-%m-%d"
                        )

                except:
                    pass

                return np.nan

            #normalize
            series = series.apply(
                normalize_date
            )

            null_indexes = series[
                series.isna()
            ].index.tolist()

            for idx in null_indexes:

                prev_vals = series.iloc[
                    :idx
                ].dropna()

                next_vals = series.iloc[
                    idx+1:
                ].dropna()

                prev_date = (

                    prev_vals.iloc[-1]

                    if not prev_vals.empty

                    else None
                )

                next_date = (

                    next_vals.iloc[0]

                    if not next_vals.empty

                    else None
                )

                # if pre exsist

                if prev_date:

                    try:

                        # shamsi
                        if "/" in prev_date:

                            y, m, d = map(
                                int,
                                prev_date.split("/")
                            )

                            jd = jdatetime.date(
                                y,
                                m,
                                d
                            )

                            new_date = (
                                jd
                                + jdatetime.timedelta(days=1)
                            )

                            final_date = (
                                f"{new_date.year:04d}/"
                                f"{new_date.month:02d}/"
                                f"{new_date.day:02d}"
                            )

                        # miladi
                        else:

                            gd = pd.to_datetime(
                                prev_date
                            )

                            gd = gd + pd.Timedelta(days=1)

                            final_date = gd.strftime(
                                "%Y-%m-%d"
                            )

                    except:

                        final_date = prev_date

                elif next_date:

                    final_date = next_date

                else:

                    final_date = "1403/01/01"

                series.at[idx] = final_date

                df.at[idx, original] = final_date

                issues.append({

                    'row': int(idx),

                    'column': original,

                    'target': target,

                    'suggested_value': final_date
                })

            df[original] = series


        #customer column
        elif target == 'customer':

            null_indexes = series[
                series.isna()
            ].index.tolist()

            for idx in null_indexes:

                series.at[idx] = "مشتری ناشناس"

                df.at[
                    idx,
                    original
                ] = "مشتری ناشناس"

            df[original] = series

        # product status

        elif target in [
            'product',
            'status'
        ]:

            null_indexes = series[
                series.isna()
            ].index.tolist()

            for idx in null_indexes:

                series.at[idx] = "نامشخص"

                df.at[
                    idx,
                    original
                ] = "نامشخص"

            df[original] = series

    return {

        'issues': issues,

        'df': df
    }



#insights

def generate_insights(df: pd.DataFrame, mapping: dict):

    rev_col = next(
        (k for k, v in mapping.items() if v == "revenue"),
        None
    )

    profit_col = next(
        (k for k, v in mapping.items() if v == "profit"),
        None
    )

    date_col = next(
        (k for k, v in mapping.items() if v == "date"),
        None
    )

    cust_col = next(
        (k for k, v in mapping.items() if v == "customer"),
        None
    )

    prod_col = next(
        (k for k, v in mapping.items() if v == "product"),
        None
    )

    insights = {
        "kpis": {},
        "text_insights": [],
        "top_customers": [],
        "top_products": []
    }

    
    # revenue
    
    if rev_col:

        revenues = df[rev_col].apply(fa_to_en)

        revenues = pd.to_numeric(
            revenues,
            errors='coerce'
        ).dropna()

        if not revenues.empty:

            insights["kpis"].update({
                "total_revenue": float(revenues.sum()),
                "total_orders": int(len(revenues)),
                "avg_order_value": int(revenues.mean())
            })

    #profit

    if profit_col:

        profits = df[profit_col].apply(fa_to_en)

        profits = pd.to_numeric(
            profits,
            errors='coerce'
        ).dropna()

        if not profits.empty:

            total_profit = float(profits.sum())

            insights["kpis"]["total_profit"] = total_profit

            if total_profit > 0:

                insights["text_insights"].append(
                    f"✅ کسب‌وکار <b>سودده</b> است "
                    f"(سود خالص: {total_profit:,.0f})"
                )

            elif total_profit < 0:

                insights["text_insights"].append(
                    f"❌ کسب‌وکار <b>ضررده</b> است "
                    f"(زیان خالص: {abs(total_profit):,.0f})"
                )

            else:

                insights["text_insights"].append(
                    "⚖️ کسب‌وکار سربه‌سر است"
                )

    # customers
    if cust_col:

        insights["kpis"]["unique_customers"] = int(
            df[cust_col].nunique()
        )

    
    # top product
    if prod_col and rev_col:

        try:

            revenue_series = df[rev_col].apply(fa_to_en)

            revenue_series = pd.to_numeric(
                revenue_series,
                errors='coerce'
            )

            temp_df = pd.DataFrame({
                "product": df[prod_col],
                "revenue": revenue_series
            }).dropna()

            top_products = temp_df.groupby(
                "product"
            )["revenue"].sum().nlargest(5)

            insights["top_products"] = [

                {
                    "name": str(name),
                    "revenue": float(revenue)
                }

                for name, revenue in top_products.items()
            ]

            insights["text_insights"].append(
                f"💎 پرفروش‌ترین محصول: "
                f"<b>{top_products.index[0]}</b>"
            )

        except:
            pass

    
    # to customers
    if cust_col and rev_col:

        try:

            revenue_series = df[rev_col].apply(fa_to_en)

            revenue_series = pd.to_numeric(
                revenue_series,
                errors='coerce'
            )

            temp_df = pd.DataFrame({
                "customer": df[cust_col],
                "revenue": revenue_series
            }).dropna()

            top_customers = temp_df.groupby(
                "customer"
            )["revenue"].sum().nlargest(5)

            insights["top_customers"] = [

                {
                    "name": str(name),
                    "revenue": float(revenue)
                }

                for name, revenue in top_customers.items()
            ]

        except:
            pass

    #analysis
    if date_col and rev_col:

        try:

            dates = df[date_col].apply(
                smart_parse_date
            )

            revenues = df[rev_col].apply(
                fa_to_en
            )

            revenues = pd.to_numeric(
                revenues,
                errors='coerce'
            )

            temp = pd.DataFrame({
                "date": dates,
                "revenue": revenues
            }).dropna()

            if not temp.empty:

                yearly = temp.groupby(
                    temp["date"].dt.year
                )["revenue"].sum()

                if len(yearly) >= 2:

                    years = yearly.index.sort_values()

                    latest_year = years[-1]
                    previous_year = years[-2]

                    latest_rev = yearly[latest_year]
                    prev_rev = yearly[previous_year]

                    growth_rate = (
                        (
                            latest_rev - prev_rev
                        ) / prev_rev * 100
                    ) if prev_rev != 0 else 0

                    insights["kpis"].update({

                        "latest_year":
                            int(latest_year),

                        "previous_year":
                            int(previous_year),

                        "growth_rate":
                            round(growth_rate, 1),

                        "latest_year_revenue":
                            float(latest_rev)
                    })

                    if growth_rate > 0:

                        insights["text_insights"].append(
                            f"📈 کسب‌وکار "
                            f"<b>{growth_rate:.1f}% رشد</b> داشته است"
                        )

                    else:

                        insights["text_insights"].append(
                            f"📉 کسب‌وکار "
                            f"<b>{abs(growth_rate):.1f}% کاهش</b> داشته است"
                        )

                if not yearly.empty:

                    best_year = yearly.idxmax()
                    best_amount = yearly.max()

                    insights["kpis"].update({

                        "best_year":
                            int(best_year),

                        "best_year_revenue":
                            float(best_amount)
                    })

                    insights["text_insights"].append(
                        f"🏆 بهترین سال: "
                        f"<b>{best_year}</b> "
                        f"با فروش "
                        f"<b>{best_amount:,.0f}</b>"
                    )

        except:
            pass

    if not insights["text_insights"]:

        insights["text_insights"].append(
            "داده کافی برای تحلیل وجود ندارد."
        )

    return insights


def clean_column_name(col: str) -> str:
    if not isinstance(col, str):
        return str(col).strip()
    import re
    col = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', col)
    col = col.replace('\xa0', ' ').replace('\u200c', '').replace('\u200e', '').replace('\u200f', '')
    col = re.sub(r'\s+', ' ', col)
    return col.strip()