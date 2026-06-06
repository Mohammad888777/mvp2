import json
import pandas as pd
import numpy as np
import io
import jdatetime
from openai import OpenAI
from typing import Dict, List, Any

client = OpenAI(
    base_url='https://api.gapgpt.app/v1',
    api_key="sk-y081hz3h5VINxFDetVZB9nBPJxy3aB8TSBi4KBft9DewXqIw",
    # api_key='sk-DlNlz3icgBGsHO9vGk0QUNUpXn5eHDIZ9pkfp3XCe1eZKRnA',
    # api_key="sk-uDrPLi9nnuROklArZD80xfWQstK19u9IvlD0Y0XMkGavX2k8",
    # api_key="sk-5IThBH7BML0zrGMzxOep6jhOaU6TWY0MUXqkaBl0i8vgYXoO",
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
 
 
 



# رسیدگی به داده‌های ناهماهنگ (ragged data) و هشدار تعداد ستون‌ها

def read_excel_file(file_content: bytes, filename: str, force_header=None):
    """
    خواندن فایل Excel یا CSV با تشخیص خودکار:
    - encoding (UTF-8, windows-1256, cp1252, ...)
    - delimiter (',' , ';' , '\t' , '|')
    - وجود header یا نبودن آن (معیار: اگر ≥30% مقادیر ردیف اول غیرعددی باشند، هدر است)
    - چندین شیت در Excel (انتخاب شیت با بیشترین داده)
    - فایل‌های بدون پسوند یا پسوند اشتباه (با magic bytes)
    - فایل‌های خراب (corrupted)
    - پاکسازی نام ستون‌ها: حذف کاراکترهای نامرئی، جایگزینی کاراکترهای غیرمجاز با _
    - محدود کردن طول نام ستون‌ها به 50 کاراکتر (truncate با ... در انتها)
    - تغییر نام خودکار هدرهای تکراری (اضافه شدن _1, _2)
    - شناسایی و نام‌گذاری خودکار هدرهای خالی یا فقط فاصله (Column_1, Column_2)
    - در صورت نبود هدر، نام ستون‌ها به صورت "Col_1", "Col_2", ... تنظیم می‌شود
    - رسیدگی به داده‌های ناهماهنگ (ragged rows): padding با NaN و هشدار
    - هشدار در صورت تعداد ستون‌های زیاد (>15)
    """
    import re
    import io
    import pandas as pd
    import numpy as np

    # ------------------------------------------
    # 0. تابع کمکی برای پاکسازی نام ستون (sanitize)
    # ------------------------------------------
    def sanitize_column_name(col: str, col_index: int = None) -> str:
        if not isinstance(col, str):
            col = str(col)
        # حذف کاراکترهای کنترلی و فاصله‌های نامرئی
        col = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', col)
        col = col.replace('\xa0', ' ').replace('\u200c', '').replace('\u200e', '').replace('\u200f', '')
        col = re.sub(r'\s+', ' ', col)
        col = col.strip()
        # جایگزینی کاراکترهای غیرمجاز با زیرخط
        invalid_chars = r'[\\/*?:\[\]{}|<>+=;,.()&%$#@!~\t\n]'
        col = re.sub(invalid_chars, '_', col)
        # حذف زیرخط‌های تکراری و حاشیه‌ای
        col = re.sub(r'_+', '_', col).strip('_')
        # محدود کردن طول به 50 کاراکتر
        if len(col) > 50:
            col = col[:50] + '...'
        # اگر نام خالی شد، نام خودکار بساز
        if not col:
            if col_index is not None:
                col = f"Column_{col_index+1}"
            else:
                col = "Column"
        return col

    # ------------------------------------------
    # 0.1 تابع کمکی برای padding داده‌های ناهماهنگ
    # ------------------------------------------
    def fix_ragged_rows(df: pd.DataFrame, expected_cols: int) -> tuple:
        """
        بررسی و اصلاح ردیف‌هایی که تعداد ستون‌های آنها با expected_cols برابر نیست.
        ردیف‌های کوتاه‌تر با NaN پر می‌شوند، ردیف‌های بلندتر بریده می‌شوند.
        برگرداندن (df_اصلاح شده, تعداد_ردیف‌های_اصلاح‌شده)
        """
        fixed_rows = 0
        new_rows = []
        for idx, row in df.iterrows():
            row_list = row.tolist()
            if len(row_list) != expected_cols:
                fixed_rows += 1
                if len(row_list) < expected_cols:
                    # اضافه کردن NaN به انتها
                    row_list.extend([np.nan] * (expected_cols - len(row_list)))
                else:
                    # بریدن ردیف‌های بلندتر
                    row_list = row_list[:expected_cols]
                new_rows.append(row_list)
            else:
                new_rows.append(row_list)
        if fixed_rows > 0:
            df_fixed = pd.DataFrame(new_rows, columns=df.columns)
            return df_fixed, fixed_rows
        return df, 0

    # ------------------------------------------
    # 1. تشخیص نوع فایل از روی محتوا (magic bytes) اگر پسوند معتبر نباشد
    # ------------------------------------------
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    allowed_extensions = ['xlsx', 'xls', 'csv']

    if ext not in allowed_extensions:
        detected_type = None
        if len(file_content) >= 4 and file_content[:4] == b'PK\x03\x04':
            detected_type = 'xlsx'
        elif len(file_content) >= 8 and file_content[:8] == b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1':
            detected_type = 'xls'
        else:
            try:
                sample = file_content[:1000].decode('utf-8', errors='ignore')
                if any(c in sample for c in [',', ';', '\t']) and not any(c in sample for c in ['\x00', '\x01']):
                    detected_type = 'csv'
            except: 
                pass
        if detected_type is None:
            raise ValueError("فرمت فایل قابل تشخیص نیست. لطفاً فایل Excel یا CSV معتبر آپلود کنید.")
        ext = detected_type

    sheet_info = {
        "has_multiple_sheets": False,
        "selected_sheet": None,
        "total_sheets": 1,
        "warning": "",
        "header_detected": True,
        "duplicate_columns_renamed": False,
        "empty_headers_filled": False,
        "truncated_headers": False,
        "ragged_rows_fixed": False,
        "too_many_columns": False
    }

    try:
        # ------------------------------------------
        # 2. خواندن فایل CSV
        # ------------------------------------------
        if ext == 'csv':
            encodings = ['utf-8', 'windows-1256', 'cp1252', 'iso-8859-1']
            df = None
            used_encoding = None
            used_sep = ','
            for enc in encodings:
                try:
                    test_df = pd.read_csv(io.BytesIO(file_content), encoding=enc, nrows=5)
                    if len(test_df.columns) >= 1:
                        df = pd.read_csv(io.BytesIO(file_content), encoding=enc)
                        used_encoding = enc
                        used_sep = ','
                        break
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
            if df is None:
                df = pd.read_csv(io.BytesIO(file_content), encoding='utf-8', errors='ignore')
                used_encoding = 'utf-8'
                used_sep = ','
                sheet_info["warning"] = "Encoding نامشخص، ممکن است کاراکترها درست نمایش داده نشوند."

            # تشخیص delimiter اگر تعداد ستون‌ها کمتر از ۲ باشد
            if len(df.columns) < 2:
                possible_seps = [',', ';', '\t', '|']
                for sep in possible_seps:
                    try:
                        test_df = pd.read_csv(io.BytesIO(file_content), encoding=used_encoding, sep=sep, nrows=5)
                        if len(test_df.columns) > 1:
                            df = pd.read_csv(io.BytesIO(file_content), encoding=used_encoding, sep=sep)
                            used_sep = sep
                            sheet_info["warning"] = (sheet_info["warning"] or "") + f" | جداکننده خودکار: '{sep}'"
                            break
                    except:
                        continue

            # تشخیص هدر (اگر force_header تعیین نشده باشد)
            if force_header is None and not df.empty:
                first_row = df.iloc[0].astype(str)
                non_numeric_count = 0
                for val in first_row:
                    try:
                        float(val.replace(',', '').replace('٬', ''))
                    except:
                        non_numeric_count += 1
                ratio_non_numeric = non_numeric_count / len(first_row) if len(first_row) > 0 else 0
                if ratio_non_numeric >= 0.3:
                    sheet_info["header_detected"] = True
                else:
                    # دوباره بخوان بدون هدر
                    df = pd.read_csv(io.BytesIO(file_content), encoding=used_encoding,
                                     sep=used_sep, header=None)
                    sheet_info["header_detected"] = False
                    sheet_info["warning"] = (sheet_info["warning"] or "") + " | فایل بدون هدر تشخیص داده شد. ردیف اول به عنوان داده در نظر گرفته شد."

            sheet_info["selected_sheet"] = "CSV File"

            # ========== رسیدگی به داده‌های ناهماهنگ (ragged rows) ==========
            expected_cols = len(df.columns)
            df, ragged_count = fix_ragged_rows(df, expected_cols)
            if ragged_count > 0:
                sheet_info["ragged_rows_fixed"] = True
                sheet_info["warning"] = (sheet_info["warning"] or "") + f" | {ragged_count} ردیف دارای تعداد ستون ناهماهنگ بودند و با NaN اصلاح شدند."

        # ------------------------------------------
        # 3. خواندن فایل Excel
        # ------------------------------------------
        else:  # xlsx یا xls
            try:
                xl = pd.ExcelFile(io.BytesIO(file_content))
            except Exception as e:
                error_msg = str(e).lower()
                if any(kw in error_msg for kw in ["bad zip file", "not a zip file", "unsupported format", "corrupted", "truncated"]):
                    raise ValueError("فایل Excel آسیب دیده یا خراب است. لطفاً فایل دیگری را امتحان کنید.")
                raise ValueError(f"خطا در خواندن فایل Excel: {str(e)}")

            sheet_names = xl.sheet_names
            sheet_info["total_sheets"] = len(sheet_names)
            if len(sheet_names) > 1:
                sheet_info["has_multiple_sheets"] = True

            # انتخاب شیت با حداقل ۲ ردیف (هدر + داده)
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

            # تشخیص هدر برای Excel (≥30% غیرعددی)
            if force_header is None and not df.empty:
                first_row = df.iloc[0].astype(str)
                non_numeric_count = 0
                for val in first_row:
                    try:
                        float(val.replace(',', '').replace('٬', ''))
                    except:
                        non_numeric_count += 1
                ratio_non_numeric = non_numeric_count / len(first_row) if len(first_row) > 0 else 0
                if ratio_non_numeric >= 0.3:
                    sheet_info["header_detected"] = True
                else:
                    df = xl.parse(selected_sheet, header=None)
                    df = df.dropna(how='all').reset_index(drop=True)
                    sheet_info["header_detected"] = False
                    sheet_info["warning"] = (sheet_info["warning"] or "") + " | فایل بدون هدر تشخیص داده شد. ردیف اول به عنوان داده در نظر گرفته شد."

            # بررسی ناهماهنگی در Excel (کمتر محتمل اما ممکن است)
            expected_cols = len(df.columns)
            df, ragged_count = fix_ragged_rows(df, expected_cols)
            if ragged_count > 0:
                sheet_info["ragged_rows_fixed"] = True
                sheet_info["warning"] = (sheet_info["warning"] or "") + f" | {ragged_count} ردیف دارای تعداد ستون ناهماهنگ بودند و با NaN اصلاح شدند."

    except Exception as e:
        if "آسیب دیده" in str(e) or "خالی است" in str(e):
            raise
        raise ValueError(f"خطا در خواندن فایل: {str(e)}")

    # ------------------------------------------
    # 4. پاکسازی نهایی و نام‌گذاری ستون‌ها
    # ------------------------------------------
    if df.empty or len(df) == 0:
        raise ValueError("فایل خالی است یا داده‌ای ندارد.")
    if len(df) == 1:
        sheet_info["warning"] = (sheet_info["warning"] or "") + " هشدار: فایل فقط شامل یک ردیف است (احتمالاً بدون داده)."

    df = df.dropna(how='all').reset_index(drop=True)

    # ========== هشدار در صورت تعداد ستون‌های زیاد ==========
    column_count = len(df.columns)
    if column_count > 15:
        sheet_info["too_many_columns"] = True
        sheet_info["warning"] = (sheet_info["warning"] or "") + f" | تعداد ستون‌های فایل زیاد است ({column_count} ستون). لطفاً فقط ستون‌های مهم را نگاشت کنید."

    if sheet_info.get("header_detected", True):
        # ========== الف) پاکسازی و truncate نام ستون‌ها ==========
        original_names = df.columns.tolist()
        new_names = []
        truncated_occurred = False
        for idx, col in enumerate(original_names):
            sanitized = sanitize_column_name(str(col), idx)
            if len(sanitized) < len(str(col)) and len(str(col)) > 50:
                truncated_occurred = True
            new_names.append(sanitized)
        df.columns = new_names
        if truncated_occurred:
            sheet_info["truncated_headers"] = True
            sheet_info["warning"] = (sheet_info["warning"] or "") + " | برخی هدرها به دلیل طول زیاد truncated شدند (محدودیت 50 کاراکتر)."

        # ========== ب) شناسایی و نام‌گذاری هدرهای خالی ==========
        cols = df.columns.tolist()
        empty_found = False
        for i, col in enumerate(cols):
            if col is None or (isinstance(col, str) and col.strip() == ''):
                cols[i] = f"Column_{i+1}"
                empty_found = True
        if empty_found:
            df.columns = cols
            sheet_info["empty_headers_filled"] = True
            sheet_info["warning"] = (sheet_info["warning"] or "") + " | هدرهای خالی با نام‌های خودکار (Column_1, Column_2, ...) پر شدند."

        # ========== ج) تغییر نام خودکار هدرهای تکراری ==========
        cols = df.columns.tolist()
        seen = {}
        new_cols = []
        duplicate_found = False
        for col in cols:
            if col in seen:
                duplicate_found = True
                seen[col] += 1
                new_name = f"{col}_{seen[col]}"
                new_cols.append(new_name)
            else:
                seen[col] = 0
                new_cols.append(col)
        if duplicate_found:
            df.columns = new_cols
            sheet_info["duplicate_columns_renamed"] = True
            sheet_info["warning"] = (sheet_info["warning"] or "") + " | هدرهای تکراری به صورت خودکار تغییر نام یافتند (اضافه شدن _1, _2)."

    else:
        # فایل بدون هدر: تولید نام ستون‌های ساده انگلیسی
        df.columns = [f"Col_{i+1}" for i in range(len(df.columns))]
        sheet_info["generated_columns"] = True
        sheet_info["warning"] = (sheet_info["warning"] or "") + " | نام ستون‌ها به صورت خودکار Col_1, Col_2,... تنظیم شد."

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
    # if amount_col and amount_col in df.columns:
    #     series = to_na(df[amount_col])
    #     series = series.apply(parse_amount)
    #     series = pd.to_numeric(series, errors='coerce')
        
    #     mean_value = series.mean()
    #     if pd.isna(mean_value) or mean_value == 0:
    #         mean_value = 0
    #     mean_value = round(float(mean_value), 2)

    #     null_indexes = series[series.isna()].index.tolist()
    #     for idx in null_indexes:
    #         df.at[idx, amount_col] = mean_value
    #         issues.append({'row': int(idx)+2, 'column': amount_col, 'target': 'amount', 'value': mean_value})

    #     df[amount_col] = series.fillna(mean_value)


    if amount_col and amount_col in df.columns:
        series = to_na(df[amount_col])
        series = series.apply(parse_amount)   # ← استفاده از parse_amount

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
# def generate_insights(df: pd.DataFrame, mapping: dict):
#     amount_col = next((k for k, v in mapping.items() if v == "amount"), None)
#     date_col = next((k for k, v in mapping.items() if v == "date"), None)
#     cust_col = next((k for k, v in mapping.items() if v == "customer"), None)
#     prod_col = next((k for k, v in mapping.items() if v == "product"), None)

#     insights = {
#         "kpis": {},
#         "text_insights": [],
#         "top_products": [],
#         "repeat_rate": 0
#     }

#     # KPI پایه
#     if amount_col:
#         revenues = pd.to_numeric(df[amount_col].apply(fa_to_en), errors='coerce').dropna()
#         if not revenues.empty:
#             insights["kpis"].update({
#                 "total_revenue": float(revenues.sum()),
#                 "total_orders": int(len(revenues)),
#                 "avg_order_value": float(revenues.mean())
#             })

#     if cust_col:
#         insights["kpis"]["unique_customers"] = int(df[cust_col].nunique())

#     # Repeat Customers
#     if cust_col and amount_col:
#         valid = df[[cust_col, amount_col]].dropna()
#         repeat = valid.groupby(cust_col).size()
#         repeat_rate = (repeat > 1).mean() * 100 if not repeat.empty else 0
#         insights["repeat_rate"] = round(repeat_rate, 1)
#         insights["text_insights"].append(f"🔄 {repeat_rate:.1f}% مشتریان تکراری هستند")

#     # Best Product
#     if prod_col and amount_col:
#         temp = df[[prod_col, amount_col]].copy()
#         temp[amount_col] = pd.to_numeric(temp[amount_col].apply(fa_to_en), errors='coerce')
#         top = temp.groupby(prod_col)[amount_col].sum().nlargest(5)
#         insights["top_products"] = [{"name": str(name), "revenue": float(val)} for name, val in top.items()]
#         if not top.empty:
#             insights["text_insights"].append(f"🏆 پرفروش‌ترین: <b>{top.index[0]}</b>")

#     # Best Day + Trend
#     if date_col and amount_col:
#         df_date = df.copy()
#         df_date[date_col] = pd.to_datetime(df_date[date_col], errors='coerce')
#         daily = df_date.groupby(df_date[date_col].dt.date)[amount_col].sum()
#         if not daily.empty:
#             best_day = daily.idxmax()
#             insights["text_insights"].append(f"📅 بهترین روز فروش: <b>{best_day}</b>")

#     if not insights["text_insights"]:
#         insights["text_insights"].append("داده کافی برای تحلیل عمیق وجود ندارد.")

#     return insights




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
        revenues = df[amount_col].apply(parse_amount).dropna()
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
        # برای محاسبه تکرار مشتری، نیازی به تبدیل amount نیست فقط وجود آن مهم است
        valid = df[[cust_col, amount_col]].dropna()
        repeat = valid.groupby(cust_col).size()
        repeat_rate = (repeat > 1).mean() * 100 if not repeat.empty else 0
        insights["repeat_rate"] = round(repeat_rate, 1)
        insights["text_insights"].append(f"🔄 {repeat_rate:.1f}% مشتریان تکراری هستند")

    # Best Product
    if prod_col and amount_col:
        temp = df[[prod_col, amount_col]].copy()
        temp[amount_col] = temp[amount_col].apply(parse_amount)
        top = temp.groupby(prod_col)[amount_col].sum().nlargest(5)
        insights["top_products"] = [{"name": str(name), "revenue": float(val)} for name, val in top.items()]
        if not top.empty:
            insights["text_insights"].append(f"🏆 پرفروش‌ترین: <b>{top.index[0]}</b>")

    # Best Day (با پشتیبانی از تاریخ شمسی و میلادی)
    if date_col and amount_col:
        # ایجاد یک کپی موقت برای تبدیل تاریخ
        temp_df = df[[date_col, amount_col]].copy()
        # تبدیل تاریخ به datetime (میلادی) برای محاسبات
        temp_df['_temp_date'] = temp_df[date_col].apply(parse_date_robust)
        temp_df = temp_df.dropna(subset=['_temp_date'])
        if not temp_df.empty:
            # تبدیل amount به عدد با parse_amount
            temp_df[amount_col] = temp_df[amount_col].apply(parse_amount)
            daily = temp_df.groupby(temp_df['_temp_date'].dt.date)[amount_col].sum()
            if not daily.empty:
                best_day = daily.idxmax()
                # پیدا کردن مقدار اصلی تاریخ (همان فرمت ورودی) برای نمایش
                original_date = temp_df[temp_df['_temp_date'].dt.date == best_day][date_col].iloc[0]
                insights["text_insights"].append(f"📅 بهترین روز فروش: <b>{original_date}</b>")

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







import re
import jdatetime
from datetime import datetime

def is_jalali_date(date_str: str) -> bool:
    """
    تشخیص شمسی بودن تاریخ بدون تبدیل.
    معیارها:
    - سال بین 1300 تا 1500
    - وجود کلمات ماه شمسی (فروردین، اردیبهشت، ...)
    - الگوی عددی مانند ۱۴۰۳/۰۳/۱۵
    """
    if not isinstance(date_str, str):
        return False
    date_str = date_str.strip()
    # الگوی عددی شمسی با جداکننده
    if re.match(r'^(13[0-9]{2}|14[0-9]{2})/(0[1-9]|1[0-2])/(0[1-9]|[12][0-9]|3[01])$', date_str):
        return True
    # شامل نام ماه شمسی
    persian_months = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 
                      'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
    if any(month in date_str for month in persian_months):
        return True
    # امتحان parse با jdatetime
    try:
        # حذف جداکننده‌ها
        cleaned = date_str.replace('/', '').replace('-', '').strip()
        if len(cleaned) == 8 and cleaned.isdigit():
            y = int(cleaned[:4])
            m = int(cleaned[4:6])
            d = int(cleaned[6:8])
            if 1300 <= y <= 1500 and 1 <= m <= 12 and 1 <= d <= 31:
                jdatetime.date(y, m, d)
                return True
    except:
        pass
    return False

def parse_date_robust(date_val):
    """
    تبدیل هر نوع تاریخ (شمسی عددی، شمسی نوشتاری، میلادی) به datetime (میلادی).
    در صورت عدم موفقیت NaT برمی‌گرداند.
    """
    if pd.isna(date_val):
        return pd.NaT
    date_str = str(date_val).strip()
    if not date_str:
        return pd.NaT
    
    # 1. اگر شمسی تشخیص داده شد
    if is_jalali_date(date_str):
        try:
            # تبدیل تاریخ شمسی به میلادی
            # فرمت‌های مختلف:
            # - "۱۴۰۳/۰۳/۱۵" یا "1403/03/15"
            # - "۵ خرداد ۱۴۰۳"
            # ابتدا سعی می‌کنیم عددی را از رشته استخراج کنیم
            parts = re.split(r'[\/\-]', date_str)
            if len(parts) == 3:
                y, m, d = map(int, parts)
                jd = jdatetime.date(y, m, d)
                return pd.Timestamp(jd.togregorian())
            else:
                # فرمت نوشتاری: مثلاً "۵ خرداد ۱۴۰۳"
                persian_months = {
                    'فروردین': 1, 'اردیبهشت': 2, 'خرداد': 3, 'تیر': 4,
                    'مرداد': 5, 'شهریور': 6, 'مهر': 7, 'آبان': 8,
                    'آذر': 9, 'دی': 10, 'بهمن': 11, 'اسفند': 12
                }
                for month_name, month_num in persian_months.items():
                    if month_name in date_str:
                        # استخراج روز و سال
                        numbers = re.findall(r'\d+', date_str)
                        if len(numbers) >= 2:
                            day = int(numbers[0])
                            year = int(numbers[1])
                            jd = jdatetime.date(year, month_num, day)
                            return pd.Timestamp(jd.togregorian())
                        break
        except Exception:
            pass
        return pd.NaT
    
    # 2. اگر میلادی است (یا شبیه میلادی)
    try:
        return pd.to_datetime(date_str, errors='coerce')
    except:
        return pd.NaT











def parse_amount(value):
    """
    تبدیل رشته مبلغ به عدد اعشاری (تومان) با مدیریت:
    - جداکننده هزارگان (٬ , فاصله)
    - اعداد فارسی
    - واحدهای تومان، ریال، هزار تومان، میلیون تومان، میلیارد تومان
    - ارزهای خارجی (دلار، یورو، دینار) بدون تبدیل
    - استخراج عدد از متن (مثل "قیمت: ۱۵۰,۰۰۰ تومان")
    - اعداد اعشاری با نقطه
    - اگر عددی یافت نشد، NaN برمی‌گرداند.
    """
    if pd.isna(value):
        return np.nan
    s = str(value).strip()
    if s == '':
        return np.nan

    # ========== استخراج عدد از متن ==========
    # الگو: عدد (با اعداد فارسی یا انگلیسی) ممکن است شامل جداکننده هزارگان (٬ یا ,) و نقطه اعشار باشد
    # ابتدا اعداد فارسی را به انگلیسی تبدیل می‌کنیم تا الگو ساده شود
    s_en = fa_to_en(s)
    # الگو: یک عدد شامل ارقام، جداکننده‌های (٬ ,) و نقطه اعشار
    # می‌خواهیم اولین عدد را پیدا کنیم (که بزرگ‌ترین احتمال مبلغ است)
    # الگو: \d+(?:[٫,]\d{3})*(?:\.\d+)?   (اعداد با هزارگان و اعشار)
    match = re.search(r'\d+(?:[٫,]\d{3})*(?:\.\d+)?', s_en)
    if match:
        num_str = match.group()
        # جایگزینی کل رشته اصلی با قسمت عددی (برای حفظ واحدهایی که ممکن است بعد از عدد باشند)
        # اما بهتر است فقط همان عدد را بگیریم و بقیه رشته را برای تشخیص واحد نادیده بگیریم
        # واحد ممکن است در جلوی عدد یا بعد از آن باشد. بنابراین فقط num_str را نگه می‌داریم
        s = num_str
    else:
        # اگر هیچ عددی پیدا نشد
        return np.nan

    # تشخیص واحد و ضریب (با اولویت عبارات بلندتر) - روی رشته اصلی و همچنین برچسب‌های متنی قبلی
    unit = 1.0
    # از رشته اصلی (قبل از استخراج عدد) برای تشخیص واحد استفاده می‌کنیم، چون واحد در متن است
    original_s = str(value).strip()
    original_s_en = fa_to_en(original_s.lower())
    patterns_unit = [
        (r'میلیارد\s*تومان', 1_000_000_000),
        (r'میلیارد', 1_000_000_000),
        (r'میلیون\s*تومان', 1_000_000),
        (r'میلیون', 1_000_000),
        (r'هزار\s*تومان', 1000),
        (r'هزار', 1000),
        (r'تومان', 1),
        (r'ریال', 0.1),
        (r'dollar|usd', 1),
        (r'euro', 1),
        (r'dinar', 1)
    ]
    for pat, mult in patterns_unit:
        if re.search(pat, original_s_en, re.IGNORECASE):
            unit = mult
            break

    # حذف جداکننده‌های هزارگان از عدد استخراج شده (فقط کاما و ویرگول فارسی)
    s = re.sub(r'[٬,]', '', s)
    # تبدیل به float (نقطه اعشار قبلاً در regex گرفته شده)
    try:
        num = float(s)
    except:
        return np.nan

    return num * unit