import json
import pandas as pd
import numpy as np
import io
import jdatetime
from openai import OpenAI
from typing import Dict, List, Any

client = OpenAI(
    base_url='https://api.gapgpt.app/v1',
    # api_key='sk-DlNlz3icgBGsHO9vGk0QUNUpXn5eHDIZ9pkfp3XCe1eZKRnA',
    api_key="sk-uDrPLi9nnuROklArZD80xfWQstK19u9IvlD0Y0XMkGavX2k8",
    timeout=60,
    max_retries=2
)

ALLOWED_FIELDS = ['amount', 'date', 'customer', 'product', 'status', 'unknown']

# =========================
# Persian / English Digits
# =========================
PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ENGLISH_DIGITS = "0123456789"

def fa_to_en(value):
    if value is None or pd.isna(value):
        return value
    value = str(value)
    for fa, en in zip(PERSIAN_DIGITS, ENGLISH_DIGITS):
        value = value.replace(fa, en)
    value = value.replace("٬", "").replace(",", "")
    return value.strip()

# =========================
# Smart Date Parser
# =========================
def smart_parse_date(value):
    if value is None or pd.isna(value):
        return pd.NaT
    value = fa_to_en(value)
    try:
        return pd.to_datetime(value)
    except:
        pass
    # Jalali
    try:
        if "/" in value or "-" in value:
            parts = value.replace("-", "/").split("/")
            if len(parts) == 3:
                y, m, d = map(int, parts)
                if y < 1700:  # شمسی
                    jd = jdatetime.date(y, m, d)
                    return pd.Timestamp(jd.togregorian())
    except:
        pass
    return pd.NaT

# =========================
# Clean Column Name
# =========================
def clean_column_name(col: str) -> str:
    if not isinstance(col, str):
        return str(col).strip()
    import re
    col = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', col)
    col = col.replace('\xa0', ' ').replace('\u200c', '').replace('\u200e', '').replace('\u200f', '')
    col = re.sub(r'\s+', ' ', col)
    return col.strip()



# =========================
# Read Excel / CSV — با پشتیبانی چندین Sheet + بازگشت اطلاعات
# =========================


# def read_excel_file(file_content: bytes, filename: str):
#     if not filename.lower().endswith(('.xlsx', '.xls', '.csv')):
#         raise ValueError("فقط فایل‌های Excel یا CSV قابل قبول هستند.")

#     sheet_info = {"has_multiple_sheets": False, "selected_sheet": None, "total_sheets": 1}

#     try:
#         if filename.lower().endswith('.csv'):
#             df = pd.read_csv(io.BytesIO(file_content))
#             sheet_info["selected_sheet"] = "CSV File"
        
#         else:
#             xl = pd.ExcelFile(io.BytesIO(file_content))
#             sheet_names = xl.sheet_names
#             sheet_info["total_sheets"] = len(sheet_names)

#             if len(sheet_names) > 1:
#                 sheet_info["has_multiple_sheets"] = True

#             # انتخاب هوشمند شیت
#             df = None
#             selected_sheet = None
            
#             for sheet in sheet_names:
#                 temp_df = xl.parse(sheet)
#                 temp_df = temp_df.dropna(how='all').reset_index(drop=True)
                
#                 if not temp_df.empty and len(temp_df) >= 1:
#                     df = temp_df
#                     selected_sheet = sheet
#                     break
            
#             if df is None:
#                 df = xl.parse(0)
#                 selected_sheet = sheet_names[0]

#             sheet_info["selected_sheet"] = selected_sheet

#     except Exception as e:
#         raise ValueError(f"خطا در خواندن فایل: {str(e)}")

#     if df.empty:
#         raise ValueError("فایل خالی است یا داده‌ای ندارد.")

#     df = df.dropna(how='all').reset_index(drop=True)
    
#     return df, sheet_info   # ← حالا دو مقدار برمی‌گرداند






# =========================
# Read Excel / CSV — هندل هوشمند Sheet خالی یا فقط هدر
# # =========================
# def read_excel_file(file_content: bytes, filename: str):
#     if not filename.lower().endswith(('.xlsx', '.xls', '.csv')):
#         raise ValueError("فقط فایل‌های Excel یا CSV قابل قبول هستند.")

#     sheet_info = {
#         "has_multiple_sheets": False, 
#         "selected_sheet": None, 
#         "total_sheets": 1,
#         "warning": None
#     }

#     try:
#         if filename.lower().endswith('.csv'):
#             df = pd.read_csv(io.BytesIO(file_content))
#             sheet_info["selected_sheet"] = "CSV File"
        
#         else:
#             xl = pd.ExcelFile(io.BytesIO(file_content))
#             sheet_names = xl.sheet_names
#             sheet_info["total_sheets"] = len(sheet_names)

#             if len(sheet_names) > 1:
#                 sheet_info["has_multiple_sheets"] = True

#             df = None
#             selected_sheet = None
            
#             # جستجوی هوشمند شیت با داده واقعی
#             for sheet in sheet_names:
#                 temp_df = xl.parse(sheet)
#                 temp_df = temp_df.dropna(how='all').reset_index(drop=True)
                
#                 # شرط قوی: حداقل ۲ ردیف (هدر + حداقل یک ردیف داده)
#                 if len(temp_df) >= 2:
#                     df = temp_df
#                     selected_sheet = sheet
#                     break
            
#             # اگر هیچ شیتی داده واقعی نداشت
#             if df is None:
#                 df = xl.parse(0).dropna(how='all').reset_index(drop=True)
#                 selected_sheet = sheet_names[0]
#                 sheet_info["warning"] = "هشدار: شیت انتخاب شده فقط شامل هدر است یا داده بسیار کمی دارد."

#             sheet_info["selected_sheet"] = selected_sheet

#     except Exception as e:
#         raise ValueError(f"خطا در خواندن فایل: {str(e)}")

#     # چک نهایی
#     if df.empty or len(df) == 0:
#         raise ValueError("فایل خالی است یا داده‌ای ندارد.")

#     if len(df) == 1:
#         sheet_info["warning"] = "هشدار: فایل فقط شامل هدر است و داده واقعی ندارد."

#     df = df.dropna(how='all').reset_index(drop=True)
    
#     return df, sheet_info





def read_excel_file(file_content: bytes, filename: str):
    if not filename.lower().endswith(('.xlsx', '.xls', '.csv')):
        raise ValueError("فقط فایل‌های Excel یا CSV قابل قبول هستند.")

    sheet_info = {
        "has_multiple_sheets": False, 
        "selected_sheet": None, 
        "total_sheets": 1,
        "warning": None
    }

    try:
        if filename.lower().endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content))
            sheet_info["selected_sheet"] = "CSV File"
        else:
            xl = pd.ExcelFile(io.BytesIO(file_content))
            sheet_names = xl.sheet_names
            sheet_info["total_sheets"] = len(sheet_names)
            if len(sheet_names) > 1:
                sheet_info["has_multiple_sheets"] = True

            df = None
            selected_sheet = None
            for sheet in sheet_names:
                temp_df = xl.parse(sheet)
                temp_df = temp_df.dropna(how='all').reset_index(drop=True)
                if len(temp_df) >= 2:
                    df = temp_df
                    selected_sheet = sheet
                    break
            if df is None:
                df = xl.parse(0).dropna(how='all').reset_index(drop=True)
                selected_sheet = sheet_names[0]
                sheet_info["warning"] = "هشدار: شیت انتخاب شده فقط شامل هدر است یا داده بسیار کمی دارد."
            sheet_info["selected_sheet"] = selected_sheet
    except Exception as e:
        raise ValueError(f"خطا در خواندن فایل: {str(e)}")

    if df.empty or len(df) == 0:
        raise ValueError("فایل خالی است یا داده‌ای ندارد.")
    if len(df) == 1:
        sheet_info["warning"] = "هشدار: فایل فقط شامل هدر است و داده واقعی ندارد."

    df = df.dropna(how='all').reset_index(drop=True)
    
    # ================== اضافه شده ==================
    # پاکسازی نام ستون‌ها از کاراکترهای نامرئی و فاصله‌های اضافی
    df.columns = [clean_column_name(col) for col in df.columns]
    # =============================================
    
    return df, sheet_info













def detect_columns_with_ai(columns: list, sample_rows: list):
    safe_rows = [
        {k: str(v)[:250] if not pd.isna(v) else None for k, v in row.items()}
        for row in sample_rows[:5]   # بیشتر نمونه داده = دقت بالاتر
    ]
     
#     prompt = f"""
# تو یک حسابدار ارشد و متخصص بسیار باتجربه تحلیل فایل‌های فروش و تراکنش‌های ایرانی هستی با بیش از ۱۵ سال تجربه.

# **ستون‌های فایل:**
# {columns}

# **نمونه داده (۵ ردیف اول):**
# {json.dumps(safe_rows, ensure_ascii=False, indent=2)}

# **فیلدهای استاندارد مورد قبول:**
# {', '.join(ALLOWED_FIELDS)}

# ### وظیفه تو تشخیص هوشمندانه مثل یک انسان واقعی است:
# - **amount**: ستون اصلی مبلغ فروش، فی فروش، جمع فاکتور، درآمد، پرداخت و ...
# - **date**: ستون تاریخ، سال، ماه، تاریخ تراکنش، سال فروش و ...
# - **customer**: ستون نام مشتری، کشور مشتری، شهر، نام خریدار، کد مشتری، منطقه و ...
# - **product**: نام محصول، کالا، شرح کالا، کد محصول و ...
# - **status**: وضعیت، نوع، بخش، دولتی/خصوصی، پروژه و ...

# **قوانین طلایی و بسیار مهم:**
# - برای هر فیلد فقط **بهترین و منطقی‌ترین** ستون را انتخاب کن.
# - اگر چند ستون مشابه بود، قوی‌ترین و اصلی‌ترین را انتخاب کن و بقیه را "unknown" بگذار.
# - از زمینه نمونه داده‌ها استفاده کن (مثلاً "کشور" در فایل فروش معمولاً معادل Customer Location است → customer).
# - اگر ستونی به شدت شبیه یکی از فیلدها بود اما دقیق نبود، باز هم هوشمندانه تصمیم بگیر.
# - هدف: دقت نزدیک به ۱۰۰٪ مثل یک انسان متخصص.

# **خروجی فقط JSON خالی بدون هیچ توضیح اضافی:**
# {{
#   "نام ستون دقیق": "amount",
#   "نام ستون دقیق": "date",
#   ...
# }}

# حالا با دقت بالا و هوش کامل نگاشت را انجام بده.
# """

    prompt = f"""
**ستون‌های فایل (اسم‌ها هر چیزی می‌توانند باشند):**
{columns}

**چند ردیف اول داده (برای درک مقادیر واقعی):**
{json.dumps(safe_rows, ensure_ascii=False, indent=2)}

**نقش‌های استاندارد مجاز (فقط همین‌ها):**
{', '.join(ALLOWED_FIELDS)}

**شما یک حسابدار باتجربه هستید. با نگاه به نام ستون و مقادیر نمونه، مانند یک انسان تصمیم بگیرید هر ستون به کدام نقش نزدیک‌تر است. از کلمات خاص یا الگوهای از پیش memorized استفاده نکنید. فقط بر اساس داده‌هایی که می‌بینید قضاوت کنید.**

**راهنمای نقش‌ها (بر اساس نوع داده و کاربرد، نه کلمات خاص):**

- **amount**: 
   - نوع داده: **عددی** (Integer, Float). مقادیر معمولاً بزرگ (مثلاً بالای چند هزار) هستند.
   - در متن تراکنش، نشان‌دهنده **مبلغ پولی نهایی** معامله است (مثل جمع فاکتور، فروش خالص). 
   - آن را با ستون‌های «تعداد» (اعداد کوچک و معمولاً زیر ۱۰۰) یا «قیمت واحد» (مبلغ هر واحد) اشتباه نگیرید. 
   - اگر ستونی عددی است ولی اسمش به «تعداد»، «سود»، «تخفیف» شبیه است، آن را به عنوان amount انتخاب نکنید مگر اینکه ستون مناسب دیگری وجود نداشته باشد.
   - **مهم**: ستون‌هایی که مقادیر متنی (شامل حروف الفبا، فاصله، نقطه) دارند هرگز amount نیستند.

- **date**:
   - مقادیر شبیه تاریخ: ترکیب اعداد با جداکننده (خط تیره، اسلش، فاصله) یا شامل نام ماه‌ها.
   - نشان‌دهنده زمان وقوع معامله.

- **customer**:
   - مقادیر متنی، معمولاً اسم، کد، موقعیت جغرافیایی یا هر چیزی که **هویت طرف معامله** (خریدار) را مشخص کند.
   - این ستون اغلب مقادیر متنوع و تکراری دارد.

- **product**:
   - مقادیر متنی که **کالا یا خدمت فروخته شده** را مشخص می‌کند (مثل نام کالا، کد محصول).
   - دسته‌بندی (مثل «لبنیات»، «نوشیدنی») را تنها در صورتی product در نظر بگیرید که ستون مجزایی برای نام خود محصول وجود نداشته باشد.

- **status**:
   - مقادیر دسته‌بندی محدود (اغلب کیفی): وضعیت سفارش، روش ارسال، نوع مشتری، بخش و ... 

- **unknown**:
   - ستون‌هایی که به هیچکدام از موارد بالا شبیه نیستند (شناسه رکورد، توضیحات اضافی، ستون‌های خالی).

**قوانین خروجی:**
1. هر نقش (amount, date, customer, product, status) حداکثر **یک بار** استفاده شود. اگر چند ستون به یک نقش شبیه بودند، فقط بهترین و اصلی‌ترین را انتخاب کنید و بقیه را "unknown" بگذارید.
2. خروجی فقط یک **JSON معتبر** باشد. هیچ متن اضافی خارج از JSON ننویسید.

اکنون نگاشت را انجام دهید. دقت کنید: به مقادیر نمونه توجه ویژه داشته باشید. مثلاً اگر ستونی با اسم عجیب دارید اما مقادیر آن اعداد بزرگ هستند، احتمال amount دارد. اگر مقادیر آن اسامی هستند، احتمال customer/product دارد.
"""




    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "تو فقط JSON معتبر خروجی می‌دهی. حتی یک کلمه هم اضافه نکن."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            timeout=50
        )
        
        suggested = json.loads(response.choices[0].message.content)
        print("#############")
        print("#############")
        print("#############")
        print(suggested)    
        print("#############")
        print("#############")
        print("#############")
        suggested = {clean_column_name(k): v for k, v in suggested.items()}
        suggested = enforce_unique_mapping(suggested, ALLOWED_FIELDS)
        print("SECOCOOCO")
        print("SECOCOOCO")
        print("SECOCOOCO")
        print(suggested)
        print("SECOCOOCO")
        print("SECOCOOCO")
        
        for col in columns:
            if col not in suggested or suggested[col] not in ALLOWED_FIELDS:
                suggested[col] = "unknown"
                
        return suggested
        
    except Exception as e:
        print("AI Column Detection Error:", e)
        return {col: "unknown" for col in columns}





# =========================
# Detect & Fix Missing Data (نسخه مقاوم)
# =========================
def detect_and_suggest_fix(df: pd.DataFrame, mapping: dict):
    df = df.copy()
    issues = []

    amount_col = next((k for k, v in mapping.items() if v == "amount"), None)
    date_col   = next((k for k, v in mapping.items() if v == "date"), None)
    cust_col   = next((k for k, v in mapping.items() if v == "customer"), None)
    prod_col   = next((k for k, v in mapping.items() if v == "product"), None)
    status_col = next((k for k, v in mapping.items() if v == "status"), None)

    # ====================== Helper: تبدیل خالی‌ها به NaN ======================
    def to_na(series):
        if series.dtype == object:
            series = series.replace(r'^\s*$', np.nan, regex=True)  # خالی یا فقط فاصله
        return series

    # ====================== AMOUNT ======================
    if amount_col and amount_col in df.columns:
        series = to_na(df[amount_col])
        series = series.apply(fa_to_en)
        series = pd.to_numeric(series, errors='coerce')
        
        mean_value = series.mean()
        if pd.isna(mean_value) or mean_value == 0:
            mean_value = 0
        mean_value = round(float(mean_value), 2)

        null_indexes = series[series.isna()].index.tolist()
        for idx in null_indexes:
            df.at[idx, amount_col] = mean_value
            issues.append({'row': int(idx)+2, 'column': amount_col, 'target': 'amount', 'value': mean_value})

        df[amount_col] = series.fillna(mean_value)

    # ====================== DATE ======================
    if date_col and date_col in df.columns:
        series = to_na(df[date_col])
        
        def fill_date(val):
            if pd.isna(val):
                return pd.NaT
            return smart_parse_date(val)
        
        series = series.apply(fill_date)
        null_indexes = series[series.isna()].index.tolist()
        
        for idx in null_indexes:
            prev_dates = series.iloc[:idx].dropna()
            next_dates = series.iloc[idx+1:].dropna()
            
            if not prev_dates.empty:
                new_date = prev_dates.iloc[-1] + pd.Timedelta(days=1)
            elif not next_dates.empty:
                new_date = next_dates.iloc[0] - pd.Timedelta(days=1)
            else:
                new_date = pd.Timestamp.today()
            
            series.at[idx] = new_date
            df.at[idx, date_col] = new_date.strftime("%Y-%m-%d")
            issues.append({'row': int(idx)+2, 'column': date_col, 'target': 'date', 'value': str(new_date.date())})

        df[date_col] = series

    # ====================== CUSTOMER ======================
    if cust_col and cust_col in df.columns:
        series = to_na(df[cust_col])
        df[cust_col] = series.fillna("مشتری ناشناس")

    # ====================== PRODUCT ======================
    if prod_col and prod_col in df.columns:
        series = to_na(df[prod_col])
        df[prod_col] = series.fillna("نامشخص")

    # ====================== STATUS ======================
    if status_col and status_col in df.columns:
        series = to_na(df[status_col])
        df[status_col] = series.fillna("نامشخص")

    return {'issues': issues, 'df': df}



# =========================
# Generate Insights (دقیق MVP)
# =========================
def generate_insights(df: pd.DataFrame, mapping: dict):
    amount_col = next((k for k, v in mapping.items() if v == "amount"), None)
    date_col = next((k for k, v in mapping.items() if v == "date"), None)
    cust_col = next((k for k, v in mapping.items() if v == "customer"), None)
    prod_col = next((k for k, v in mapping.items() if v == "product"), None)

    insights = {
        "kpis": {},
        "text_insights": [],
        "top_products": [],
        "repeat_rate": 0
    }

    # KPI پایه
    if amount_col:
        revenues = pd.to_numeric(df[amount_col].apply(fa_to_en), errors='coerce').dropna()
        if not revenues.empty:
            insights["kpis"].update({
                "total_revenue": float(revenues.sum()),
                "total_orders": int(len(revenues)),
                "avg_order_value": float(revenues.mean())
            })

    if cust_col:
        insights["kpis"]["unique_customers"] = int(df[cust_col].nunique())

    # Repeat Customers
    if cust_col and amount_col:
        valid = df[[cust_col, amount_col]].dropna()
        repeat = valid.groupby(cust_col).size()
        repeat_rate = (repeat > 1).mean() * 100 if not repeat.empty else 0
        insights["repeat_rate"] = round(repeat_rate, 1)
        insights["text_insights"].append(f"🔄 {repeat_rate:.1f}% مشتریان تکراری هستند")

    # Best Product
    if prod_col and amount_col:
        temp = df[[prod_col, amount_col]].copy()
        temp[amount_col] = pd.to_numeric(temp[amount_col].apply(fa_to_en), errors='coerce')
        top = temp.groupby(prod_col)[amount_col].sum().nlargest(5)
        insights["top_products"] = [{"name": str(name), "revenue": float(val)} for name, val in top.items()]
        if not top.empty:
            insights["text_insights"].append(f"🏆 پرفروش‌ترین: <b>{top.index[0]}</b>")

    # Best Day + Trend
    if date_col and amount_col:
        df_date = df.copy()
        df_date[date_col] = pd.to_datetime(df_date[date_col], errors='coerce')
        daily = df_date.groupby(df_date[date_col].dt.date)[amount_col].sum()
        if not daily.empty:
            best_day = daily.idxmax()
            insights["text_insights"].append(f"📅 بهترین روز فروش: <b>{best_day}</b>")

    if not insights["text_insights"]:
        insights["text_insights"].append("داده کافی برای تحلیل عمیق وجود ندارد.")

    return insights






def enforce_unique_mapping(suggested: dict, allowed_fields: list) -> dict:
    used = set()
    result = {}
    for col, target in suggested.items():
        if target in allowed_fields and target not in used:
            result[col] = target
            used.add(target)
        else:
            result[col] = "unknown"
    return result