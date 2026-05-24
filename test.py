


import re
import pandas as pd
from typing import List, Dict, Any, Tuple

# ============================================================
# الگوهای regex برای هر فیلد (با امتیاز)
# ============================================================
PATTERNS = {
    'revenue': {
        'regex': re.compile(r'(?i)\b(?:فروش|درآمد|total|revenue|مبلغ|قیمت کل|price|amount)\b'),
        'weight': 0.9
    },
    'quantity': {
        'regex': re.compile(r'(?i)\b(?:تعداد|عدد|quantity|count|تیره?)\b'),
        'weight': 0.9
    },
    'profit': {
        'regex': re.compile(r'(?i)\b(?:سود\s*(?:خالص)?|profit|سوددهی)\b'),
        'weight': 0.9
    },
    'date': {
        'regex': re.compile(r'(?i)\b(?:تاریخ|سال|ماه|روز|date|year|month|day|زمان|ثبت)\b'),
        'weight': 0.9
    },
    'product': {
        'regex': re.compile(r'(?i)\b(?:محصول|کالا|product|item|کدکالا|نام محصول)\b'),
        'weight': 0.9
    },
    'customer': {
        'regex': re.compile(r'(?i)\b(?:مشتری|خریدار|customer|client|buyer|شخص|نام سفارش‌دهنده)\b'),
        'weight': 0.9
    },
    'status': {
        'regex': re.compile(r'(?i)\b(?:وضعیت|حالت|status|state|مرحله)\b'),
        'weight': 0.8
    }
}

# استثناها (امتیاز صفر)
EXCEPTION_PATTERNS = [
    re.compile(r'(?i)فی\s*فروش'),
    re.compile(r'(?i)قیمت\s*واحد'),
    re.compile(r'(?i)واحد\s*فروش'),
    re.compile(r'(?i)قیمت\s*تک'),
]

# ============================================================
# تشخیص نوع مقدار (برای نمونه داده‌ها)
# ============================================================
def infer_value_type(value: Any) -> str:
    """تشخیص نوع مقدار: numeric, date, text, null"""
    if pd.isna(value):
        return 'null'

    s = str(value).strip()
    s_clean = s.replace(',', '').replace('٬', '').strip()

    # عدد خالص
    try:
        float(s_clean)
        # اگر عدد ۴ رقمی و در بازه سال شمسی/میلادی باشد، به عنوان تاریخ در نظر بگیر
        if s_clean.isdigit() and len(s_clean) == 4:
            y = int(s_clean)
            if (1300 <= y <= 1500) or (1900 <= y <= 2030):
                return 'date'
        return 'numeric'
    except:
        pass

    # تاریخ با جداکننده یا نام ماه
    date_indicators = ['/', '-', 'اردیبهشت', 'مهر', 'آبان', 'دی', 'بهمن', 'اسفند',
                       'فروردین', 'تیر', 'مرداد', 'شهریور', 'آذر', 'Jan', 'Feb']
    if any(ind in s for ind in date_indicators):
        return 'date'

    return 'text'

# ============================================================
# محاسبه امتیاز اطمینان بر اساس نام ستون
# ============================================================
def score_by_column_name(column_name: str, field: str) -> float:
    """امتیاز تطابق نام ستون با فیلد مورد نظر (0 تا 1)"""
    col_lower = column_name.lower().strip()
    # بررسی استثناها
    for pat in EXCEPTION_PATTERNS:
        if pat.search(column_name):
            return 0.0
    # بررسی الگوی فیلد
    if field in PATTERNS:
        if PATTERNS[field]['regex'].search(col_lower):
            return PATTERNS[field]['weight']
    return 0.0

# ============================================================
# محاسبه امتیاز بر اساس نمونه داده‌ها
# ============================================================
def score_by_samples(sample_values: List[Any], field: str) -> float:
    """امتیاز تطابق نمونه داده‌ها با فیلد مورد نظر (0 تا 1)"""
    if not sample_values:
        return 0.0
    
    # حذف مقادیر خالی
    sample_values = [v for v in sample_values if pd.notna(v)]
    if not sample_values:
        return 0.0
    
    # تشخیص نوع غالب
    type_counts = {'numeric': 0, 'date': 0, 'text': 0}
    for val in sample_values[:10]:
        t = infer_value_type(val)
        type_counts[t] += 1
    max_type = max(type_counts, key=type_counts.get)
    
    # امتیاز بر اساس فیلد و نوع داده
    if field == 'revenue' and max_type == 'numeric':
        return 0.8
    if field == 'quantity' and max_type == 'numeric':
        return 0.8
    if field == 'profit' and max_type == 'numeric':
        return 0.8
    if field == 'date' and max_type == 'date':
        return 0.9
    if field == 'product' and max_type == 'text':
        return 0.6
    if field == 'customer' and max_type == 'text':
        return 0.7
    if field == 'status' and max_type == 'text':
        return 0.6
    return 0.2

# ============================================================
# تابع اصلی تشخیص با confidence score
# ============================================================
def detect_columns_rule_based(
    columns: List[str],
    sample_rows: List[Dict[str, Any]],
    name_weight: float = 0.7,
    sample_weight: float = 0.3,
    threshold: float = 0.6
) -> Dict[str, Tuple[str, float]]:
    """
    تشخیص نوع هر ستون و محاسبه امتیاز اطمینان.
    خروجی: دیکشنری {نام ستون: (فیلد پیشنهادی, امتیاز اطمینان)}
    """
    result = {}
    
    for col in columns:
        best_field = 'unknown'
        best_total_score = 0.0
        
        # بررسی تمام فیلدهای ممکن
        for field in PATTERNS.keys():
            name_score = score_by_column_name(col, field)
            if name_score == 0.0:
                continue
            
            # محاسبه امتیاز نمونه‌ها
            sample_values = []
            for row in sample_rows:
                if col in row:
                    sample_values.append(row[col])
            sample_score = score_by_samples(sample_values, field)
            
            # امتیاز نهایی
            total_score = (name_score * name_weight) + (sample_score * sample_weight)
            if total_score > best_total_score:
                best_total_score = total_score
                best_field = field
        
        # اگر هیچ فیلدی با نام_score > 0 وجود نداشت، unknown با امتیاز 0
        if best_total_score == 0.0:
            best_field = 'unknown'
            best_total_score = 0.0
        # اگر امتیاز از آستانه کمتر است، unknown
        elif best_total_score < threshold:
            best_field = 'unknown'
            # امتیاز را همان best_total_score نگه می‌داریم (کمتر از آستانه)
        
        result[col] = (best_field, round(best_total_score, 3))
    
    return result

# ============================================================
# مثال استفاده (CLI)
# ============================================================
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python detect_columns.py <file.xlsx>")
        sys.exit(1)

    file_path = sys.argv[1]

    if file_path.lower().endswith('.csv'):
        df = pd.read_csv(file_path)
    else:
        df = pd.read_excel(file_path, engine='openpyxl')

    sample_rows = df.head(3).to_dict(orient='records')
    mapping = detect_columns_rule_based(df.columns.tolist(), sample_rows)

    print("\n📊 نتیجه تشخیص ستون‌ها با Confidence Score:\n")
    print(f"{'نام ستون':<20} → {'فیلد پیشنهادی':<15} {'امتیاز اطمینان':<10}")
    print("-" * 50)
    for col, (field, score) in mapping.items():
        print(f"{col:<20} → {field:<15} {score:<10}")