import os
import uuid
import json
import time
from datetime import datetime

import pandas as pd
from django.shortcuts import render, redirect
from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings

from .models import User, Report
from .forms import UploadFileForm, ProcessForm
from .utils import (
    read_excel_file, detect_columns_with_ai, detect_and_suggest_fix,
    generate_insights, clean_column_name, ALLOWED_FIELDS,
    enforce_unique_mapping,
    
)


# ------------------- Helper: clean old files -------------------
def clean_old_pickle_files(max_age_seconds=3600):
    now = time.time()
    for fname in os.listdir(settings.MEDIA_ROOT):
        if fname.endswith('.pkl') or fname.endswith('_cleaned.xlsx'):
            path = os.path.join(settings.MEDIA_ROOT, fname)
            if os.path.isfile(path) and os.path.getmtime(path) < now - max_age_seconds:
                try:
                    os.remove(path)
                except:
                    pass


# ------------------- Home -------------------
def home(request):
    return render(request, 'index.html')


# ------------------- Auth APIs -------------------
@require_http_methods(["POST"])
@csrf_exempt
def api_login(request):
    data = json.loads(request.body)
    email = data.get('email')
    if not email:
        return JsonResponse({'error': 'ایمیل الزامی است'}, status=400)
    user, created = User.objects.get_or_create(email=email)
    request.session['user_id'] = str(user.id)
    request.session['email'] = user.email
    request.session['is_guest'] = False
    return JsonResponse({'success': True, 'user_id': user.id, 'email': user.email})

@require_http_methods(["POST"])
@csrf_exempt
def guest_login(request):
    request.session['is_guest'] = True
    request.session['guest_expire'] = time.time() + 3600
    return JsonResponse({'success': True, 'guest': True})

def me(request):
    if request.session.get('is_guest'):
        expire = request.session.get('guest_expire')
        if expire and time.time() > expire:
            request.session.flush()
            return JsonResponse({'authenticated': False})
        return JsonResponse({'authenticated': True, 'guest': True})
    if request.session.get('user_id'):
        return JsonResponse({
            'authenticated': True,
            'guest': False,
            'email': request.session.get('email'),
            'user_id': request.session.get('user_id')
        })
    return JsonResponse({'authenticated': False})

@require_http_methods(["POST"])
@csrf_exempt
def logout(request):
    request.session.flush()
    return JsonResponse({'success': True})






# @require_http_methods(["POST"])
# @csrf_exempt
# def upload_file(request):
#     if not request.session.get('user_id') and not request.session.get('is_guest'):
#         return JsonResponse({'error': 'Unauthorized'}, status=401)

#     form = UploadFileForm(request.POST, request.FILES)
#     if not form.is_valid():
#         return JsonResponse({'error': 'فایل ارسال نشده'}, status=400)

#     uploaded_file = request.FILES['file']
#     file_size_mb = uploaded_file.size / (1024 * 1024)  # تبدیل به مگابایت

#     # چک کردن حجم فایل
#     if file_size_mb > 5:
#         return JsonResponse({
#             'error': f'فایل خیلی بزرگ است ({file_size_mb:.1f} MB). حداکثر حجم مجاز ۵ مگابایت است.',
#             'max_size_exceeded': True
#         }, status=400)

#     content = uploaded_file.read()

#     try:
#         df, sheet_info = read_excel_file(content, uploaded_file.name)
#     except Exception as e:
#         return JsonResponse({'error': str(e)}, status=400)

#     session_id = str(uuid.uuid4())
#     temp_path = os.path.join(settings.MEDIA_ROOT, f"{session_id}.pkl")
#     os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
#     df.to_pickle(temp_path)

#     request.session['last_filename'] = uploaded_file.name

#     sample_rows = df.head(3).to_dict(orient='records')
#     suggested = detect_columns_with_ai(df.columns.tolist(), sample_rows)

#     return JsonResponse({
#         'session_id': session_id,
#         'columns': df.columns.tolist(),
#         'suggested_mapping': suggested,
#         'sheet_info': sheet_info,
#         'file_size_mb': round(file_size_mb, 2)
#     })



@require_http_methods(["POST"])
@csrf_exempt
def upload_file(request):
    if not request.session.get('user_id') and not request.session.get('is_guest'):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    form = UploadFileForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({'error': 'فایل ارسال نشده'}, status=400)

    uploaded_file = request.FILES['file']
    file_size_kb = uploaded_file.size / 1024   # کیلوبایت
 
    # حد تست: بیشتر از ۵۰ کیلوبایت
    if file_size_kb > 5000:
        return JsonResponse({
            'error': f'فایل خیلی بزرگ است ({file_size_kb:.1f} KB). حداکثر حجم مجاز برای تست ۵۰ کیلوبایت است.',
            'max_size_exceeded': True,
            'file_size_kb': round(file_size_kb, 1)
        }, status=400)

    content = uploaded_file.read()

    try:
        df, sheet_info = read_excel_file(content, uploaded_file.name)
        request.session['sheet_info'] = sheet_info
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

    session_id = str(uuid.uuid4())
    temp_path = os.path.join(settings.MEDIA_ROOT, f"{session_id}.pkl")
    os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
    df.to_pickle(temp_path)

    request.session['last_filename'] = uploaded_file.name

    sample_rows = df.head(3).to_dict(orient='records')
    suggested = detect_columns_with_ai(df.columns.tolist(), sample_rows)

    return JsonResponse({
        'session_id': session_id,
        'columns': df.columns.tolist(),
        'suggested_mapping': suggested,
        'sheet_info': sheet_info,
        'file_size_kb': round(file_size_kb, 1)
    })


# # ------------------- Mapping Page -------------------
# def mapping_page(request, session_id):
#     """صفحه اختصاصی برای نگاشت ستون‌ها"""
#     if not request.session.get('user_id') and not request.session.get('is_guest'):
#         return redirect('/?error=login')

#     file_path = os.path.join(settings.MEDIA_ROOT, f"{session_id}.pkl")
#     if not os.path.exists(file_path):
#         return render(request, 'error.html', {'message': 'جلسه منقضی شده یا فایل وجود ندارد'})

#     df = pd.read_pickle(file_path)
#     sample_rows = df.head(3).to_dict(orient='records')
#     suggested,sec_suggested = detect_columns_with_ai(df.columns.tolist(), sample_rows)

#     context = {
#         'session_id': session_id,
#         'columns': df.columns.tolist(),
#         'suggested_mapping': suggested,
#         'allowed_fields': ALLOWED_FIELDS,
#         "sec_suggested":sec_suggested
#     }
#     return render(request, 'mapping.html', context)



def mapping_page(request, session_id):
    if not request.session.get('user_id') and not request.session.get('is_guest'):
        return redirect('/?error=login')

    file_path = os.path.join(settings.MEDIA_ROOT, f"{session_id}.pkl")
    if not os.path.exists(file_path):
        return render(request, 'error.html', {'message': 'جلسه منقضی شده یا فایل وجود ندارد'})

    df = pd.read_pickle(file_path)
    sample_rows = df.head(3).to_dict(orient='records')
    
    suggested = detect_columns_with_ai(df.columns.tolist(), sample_rows)   # فقط یک مقدار

    
    sheet_info = request.session.pop('sheet_info', None)

    context = {
        'session_id': session_id,
        'columns': [clean_column_name(col) for col in df.columns.tolist()],
        'suggested_mapping': suggested,
        'allowed_fields': ALLOWED_FIELDS,
        'sheet_info': sheet_info,   # ← اضافه شد
    }
    return render(request, 'mapping.html', context)





# ------------------- Process API -------------------
# @require_http_methods(["POST"])
# @csrf_exempt
# def process_data(request):
#     form = ProcessForm(request.POST)
#     if not form.is_valid():
#         return JsonResponse({'error': 'داده‌های نامعتبر'}, status=400)

#     session_id = form.cleaned_data['session_id']
#     mapping_str = form.cleaned_data['mapping']
#     try:
#         mapping_dict = json.loads(mapping_str)
#     except:
#         return JsonResponse({'error': 'mapping JSON نامعتبر'}, status=400)

#     file_path = os.path.join(settings.MEDIA_ROOT, f"{session_id}.pkl")
#     if not os.path.exists(file_path):
#         return JsonResponse({'error': 'Session منقضی شده'}, status=400)

#     df = pd.read_pickle(file_path)

#     # پاکسازی نام ستون‌ها
#     df.columns = [clean_column_name(col) for col in df.columns]

#     # اصلاح داده‌ها
#     issues_dict = detect_and_suggest_fix(df, mapping_dict)
#     df_cleaned = issues_dict['df'].copy()

#     ALLOWED_EXPORT_COLUMNS = {'date', 'product', 'customer', 'quantity', 'profit', 'revenue'}
#     keep_columns = {}
#     for original_col, target in mapping_dict.items():
#         if target not in ALLOWED_EXPORT_COLUMNS:
#             continue
#         clean_col = clean_column_name(original_col)
#         if clean_col in df_cleaned.columns:
#             keep_columns[clean_col] = target
#         elif original_col in df_cleaned.columns:
#             keep_columns[original_col] = target

#     existing_cols = [col for col in keep_columns.keys() if col in df_cleaned.columns]
#     df_cleaned = df_cleaned[existing_cols].copy()
#     df_cleaned.rename(columns=keep_columns, inplace=True)
#     df_cleaned = df_cleaned.loc[:, ~df_cleaned.columns.duplicated()]

#     cleaned_path = os.path.join(settings.MEDIA_ROOT, f"{session_id}_cleaned.xlsx")
#     df_cleaned.to_excel(cleaned_path, index=False)

#     final_mapping = {col: col for col in df_cleaned.columns}
#     insights = generate_insights(df_cleaned, final_mapping)

#     # ---------- ذخیره در تاریخچه ----------
#     filename = request.session.get('last_filename', f"{session_id}.xlsx")



#     if request.session.get('is_guest'):
#         # مدیریت تاریخچه مهمان
#         history = request.session.get('guest_history', [])
#         now_ts = time.time()
#         # حذف آیتم‌های منقضی شده
#         history = [h for h in history if now_ts - h['created_at'] < 3600]
        
#         # بررسی وجود session_id تکراری
#         existing_index = None
#         for i, item in enumerate(history):
#             if item.get('session_id') == session_id:
#                 existing_index = i
#                 break
        
#         if existing_index is not None:
#             # به‌روزرسانی آیتم موجود (timestamp و insights می‌توانند تغییر کنند)
#             history[existing_index]['created_at'] = now_ts
#             history[existing_index]['insights'] = insights
#             history[existing_index]['mapping'] = mapping_dict
#             # filename احتمالاً ثابت است، ولی در صورت نیاز می‌توان به‌روز کرد
#         else:
#             # اضافه کردن آیتم جدید
#             history.append({
#                 'session_id': session_id,
#                 'filename': filename,
#                 'created_at': now_ts,
#                 'mapping': mapping_dict,
#                 'insights': insights
#             })
        
#         request.session['guest_history'] = history

#     else:
#         # کاربر لاگین شده: بررسی وجود گزارش در دیتابیس
#         user_id = request.session.get('user_id')
#         if user_id:
#             try:
#                 user = User.objects.get(id=user_id)
#                 # اگر قبلاً برای این session_id گزارشی وجود دارد، آن را به‌روز نمی‌کنیم (یا می‌توان به‌روز کرد)
#                 report, created = Report.objects.get_or_create(
#                     session_id=session_id,
#                     user=user,
#                     defaults={
#                         'filename': filename,
#                         'mapping': mapping_dict,
#                         'insights': insights
#                     }
#                 )
#                 if not created:
#                     # اگر رکورد قبلاً وجود دارد، می‌توانید فیلدهای دلخواه را به‌روز کنید
#                     report.filename = filename
#                     report.mapping = mapping_dict
#                     report.insights = insights
#                     report.save()
#             except Exception as e:
#                 print(f"Error saving report: {e}")

#     return JsonResponse({
#         'insights': insights,
#         'download_url': f'/api/download-cleaned/{session_id}'
#     })







# @require_http_methods(["POST"])
# @csrf_exempt
# def process_data(request):
#     form = ProcessForm(request.POST)
#     if not form.is_valid():
#         return JsonResponse({'error': 'داده‌های نامعتبر'}, status=400)

#     session_id = form.cleaned_data['session_id']
#     mapping_str = form.cleaned_data['mapping']
#     try:
#         mapping_dict = json.loads(mapping_str)
#     except:
#         return JsonResponse({'error': 'mapping JSON نامعتبر'}, status=400)

#     file_path = os.path.join(settings.MEDIA_ROOT, f"{session_id}.pkl")
#     if not os.path.exists(file_path):
#         return JsonResponse({'error': 'Session منقضی شده'}, status=400)

#     df = pd.read_pickle(file_path)
    
#     # پاکسازی نام ستون‌ها
#     df.columns = [clean_column_name(col) for col in df.columns]

#     # اصلاح داده‌های خالی
#     issues_dict = detect_and_suggest_fix(df, mapping_dict)
#     df_cleaned = issues_dict['df'].copy()

#     # ====================== اصلاح مهم ======================
#     # فقط ستون‌هایی که map شده‌اند را نگه دار
#     keep_columns = {}
#     for original_col, target in mapping_dict.items():
#         if target == "unknown":
#             continue
#         clean_col = clean_column_name(original_col)
#         if clean_col in df_cleaned.columns:
#             keep_columns[clean_col] = target
#         elif original_col in df_cleaned.columns:
#             keep_columns[original_col] = target

#     if not keep_columns:
#         return JsonResponse({'error': 'هیچ ستونی map نشده است'}, status=400)

#     # فیلتر ستون‌ها
#     existing_cols = [col for col in keep_columns.keys() if col in df_cleaned.columns]
#     df_cleaned = df_cleaned[existing_cols].copy()

#     # Rename به نام فیلد استاندارد (amount, date, ...)
#     df_cleaned.rename(columns=keep_columns, inplace=True)

#     # حذف ستون‌های تکراری (در صورت وجود)
#     df_cleaned = df_cleaned.loc[:, ~df_cleaned.columns.duplicated()]

#     # ====================== فرمت تاریخ ======================
#     date_col = next((col for col in df_cleaned.columns if col == "date"), None)
#     if date_col:
#         df_cleaned[date_col] = pd.to_datetime(df_cleaned[date_col], errors='coerce')
#         df_cleaned[date_col] = df_cleaned[date_col].dt.strftime("%Y-%m-%d")

#     # ذخیره فایل
#     cleaned_path = os.path.join(settings.MEDIA_ROOT, f"{session_id}_cleaned.xlsx")
#     df_cleaned.to_excel(cleaned_path, index=False)

#     final_mapping = {col: col for col in df_cleaned.columns}
#     insights = generate_insights(df_cleaned, final_mapping)

#     # ---------- ذخیره در تاریخچه (بدون تغییر) ----------
#     filename = request.session.get('last_filename', f"{session_id}.xlsx")
    
#     # ... (بقیه کد تاریخچه همان قبلی بماند)

#     return JsonResponse({
#         'insights': insights,
#         'download_url': f'/api/download-cleaned/{session_id}'
#     })




@require_http_methods(["POST"])
@csrf_exempt
def process_data(request):
    form = ProcessForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'error': 'داده‌های نامعتبر'}, status=400)

    session_id = form.cleaned_data['session_id']
    mapping_str = form.cleaned_data['mapping']
    try:
        mapping_dict = json.loads(mapping_str)
    except:
        return JsonResponse({'error': 'mapping JSON نامعتبر'}, status=400)

    # ========== پاکسازی کلیدهای mapping_dict (حذف کاراکترهای نامرئی) ==========
    mapping_dict = {clean_column_name(k): v for k, v in mapping_dict.items()}

    file_path = os.path.join(settings.MEDIA_ROOT, f"{session_id}.pkl")
    if not os.path.exists(file_path):
        return JsonResponse({'error': 'Session منقضی شده'}, status=400)

    df = pd.read_pickle(file_path)

    # پاکسازی نام ستون‌های دیتافریم (اگر قبلاً در read_excel_file انجام نشده باشد)
    df.columns = [clean_column_name(col) for col in df.columns]

    # اصلاح داده‌های خالی (با استفاده از mapping_dict پاک‌شده)
    issues_dict = detect_and_suggest_fix(df, mapping_dict)
    df_cleaned = issues_dict['df'].copy()

    # فقط ستون‌هایی که map شده‌اند را نگه دار (غیر از unknown)
    keep_columns = {}
    for original_col, target in mapping_dict.items():
        if target == "unknown":
            continue
        # original_col قبلاً clean شده، مستقیماً چک می‌کنیم
        if original_col in df_cleaned.columns:
            keep_columns[original_col] = target

    if not keep_columns:
        return JsonResponse({'error': 'هیچ ستونی map نشده است'}, status=400)

    # فیلتر ستون‌ها
    existing_cols = [col for col in keep_columns.keys() if col in df_cleaned.columns]
    df_cleaned = df_cleaned[existing_cols].copy()

    # تغییر نام ستون‌ها به نقش استاندارد (amount, date, ...)
    df_cleaned.rename(columns=keep_columns, inplace=True)

    # حذف ستون‌های تکراری احتمالی
    df_cleaned = df_cleaned.loc[:, ~df_cleaned.columns.duplicated()]

    # فرمت تاریخ (اگر ستون date وجود داشته باشد)
    date_col = next((col for col in df_cleaned.columns if col == "date"), None)
    if date_col:
        df_cleaned[date_col] = pd.to_datetime(df_cleaned[date_col], errors='coerce')
        df_cleaned[date_col] = df_cleaned[date_col].dt.strftime("%Y-%m-%d")

    # ذخیره فایل cleaned
    cleaned_path = os.path.join(settings.MEDIA_ROOT, f"{session_id}_cleaned.xlsx")
    df_cleaned.to_excel(cleaned_path, index=False)

    final_mapping = {col: col for col in df_cleaned.columns}
    insights = generate_insights(df_cleaned, final_mapping)

    # ---------- ذخیره در تاریخچه (مهمان یا کاربر لاگین) ----------
    filename = request.session.get('last_filename', f"{session_id}.xlsx")

    if request.session.get('is_guest'):
        history = request.session.get('guest_history', [])
        now_ts = time.time()
        # حذف آیتم‌های منقضی شده (بیشتر از ۱ ساعت)
        history = [h for h in history if now_ts - h.get('created_at', 0) < 3600]
        # بروزرسانی یا اضافه کردن آیتم جدید
        existing_index = None
        for i, item in enumerate(history):
            if item.get('session_id') == session_id:
                existing_index = i
                break
        if existing_index is not None:
            history[existing_index]['created_at'] = now_ts
            history[existing_index]['insights'] = insights
            history[existing_index]['mapping'] = mapping_dict
        else:
            history.append({
                'session_id': session_id,
                'filename': filename,
                'created_at': now_ts,
                'mapping': mapping_dict,
                'insights': insights
            })
        request.session['guest_history'] = history
    else:
        user_id = request.session.get('user_id')
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                report, created = Report.objects.get_or_create(
                    session_id=session_id,
                    user=user,
                    defaults={
                        'filename': filename,
                        'mapping': mapping_dict,
                        'insights': insights
                    }
                )
                if not created:
                    report.filename = filename
                    report.mapping = mapping_dict
                    report.insights = insights
                    report.save()
            except Exception as e:
                print(f"Error saving report: {e}")

    return JsonResponse({
        'insights': insights,
        'download_url': f'/api/download-cleaned/{session_id}'
    })




# ------------------- Download cleaned file -------------------
def download_cleaned(request, session_id):
    file_path = os.path.join(settings.MEDIA_ROOT, f"{session_id}_cleaned.xlsx")
    if not os.path.exists(file_path):
        return JsonResponse({'error': 'فایل پیدا نشد'}, status=404)
    return FileResponse(open(file_path, 'rb'), as_attachment=True, filename='cleaned_data.xlsx')


# ------------------- History Page & API -------------------
def history_page(request):
    """صفحه نمایش تاریخچه تحلیل‌ها"""
    if not request.session.get('user_id') and not request.session.get('is_guest'):
        return redirect('/?error=login')
    return render(request, 'history.html')



@require_http_methods(["GET"])
def get_history(request):
    """بازگرداندن تاریخچه (JSON) برای استفاده در صفحه history.html"""
    if request.session.get('is_guest'):
        history = request.session.get('guest_history', [])
        now_ts = time.time()
        valid = [h for h in history if now_ts - h['created_at'] < 3600]
        request.session['guest_history'] = valid
        return JsonResponse({'history': valid})
    else:
        user_id = request.session.get('user_id')
        if not user_id:
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        try:
            user = User.objects.get(id=user_id)
            reports = Report.objects.filter(user=user)
            history = []
            for r in reports:
                history.append({
                    'session_id': r.session_id,
                    'filename': r.filename,
                    'created_at': r.created_at.timestamp(),
                    'mapping': r.mapping,
                    'insights': r.insights
                })
            return JsonResponse({'history': history})
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)

