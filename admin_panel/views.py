from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta
from base.models import User, Report
import json

@staff_member_required
def dashboard(request):
    """داشبورد اصلی ادمین"""
    total_users = User.objects.count()
    total_reports = Report.objects.count()
    recent_reports = Report.objects.order_by('-created_at')[:10]
    
    # آمار هفتگی
    week_ago = timezone.now() - timedelta(days=7)
    new_users_week = User.objects.filter(date_joined__gte=week_ago).count()
    new_reports_week = Report.objects.filter(created_at__gte=week_ago).count()
    
    # پربازدیدترین فایل‌ها (بر اساس تعداد دفعات پردازش مجدد نمی‌توانیم، فقط آخرین‌ها)
    # در اینجا می‌توانیم از تعداد گزارش‌های هر کاربر استفاده کنیم
    users_with_most_reports = User.objects.annotate(
        report_count=Count('reports')
    ).order_by('-report_count')[:5]
    
    context = {
        'total_users': total_users,
        'total_reports': total_reports,
        'new_users_week': new_users_week,
        'new_reports_week': new_reports_week,
        'recent_reports': recent_reports,
        'users_with_most_reports': users_with_most_reports,
    }
    return render(request, 'admin_panel/dashboard.html', context)

@staff_member_required
def user_list(request):
    """لیست تمام کاربران با قابلیت جستجو"""
    query = request.GET.get('q', '')
    users = User.objects.all()
    if query:
        users = users.filter(
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(phone_number__icontains=query)
        )
    users = users.annotate(report_count=Count('reports')).order_by('-date_joined')
    context = {
        'users': users,
        'query': query,
    }
    return render(request, 'admin_panel/users.html', context)

@staff_member_required
def user_detail(request, user_id):
    """جزییات یک کاربر + تمام گزارش‌های او"""
    user = get_object_or_404(User, id=user_id)
    reports = Report.objects.filter(user=user).order_by('-created_at')
    total_revenue = 0
    for r in reports:
        insights = r.insights
        if insights and 'kpis' in insights:
            total_revenue += insights['kpis'].get('total_revenue', 0)
    context = {
        'user': user,
        'reports': reports,
        'total_revenue': total_revenue,
    }
    return render(request, 'admin_panel/user_detail.html', context)

@staff_member_required
def report_list(request):
    """لیست تمام گزارش‌ها (فایل‌های آپلود شده) با فیلتر"""
    query = request.GET.get('q', '')
    reports = Report.objects.select_related('user').all()
    if query:
        reports = reports.filter(
            Q(filename__icontains=query) |
            Q(user__email__icontains=query) |
            Q(session_id__icontains=query)
        )
    reports = reports.order_by('-created_at')
    context = {
        'reports': reports,
        'query': query,
    }
    return render(request, 'admin_panel/reports.html', context)

@staff_member_required
def report_detail(request, report_id):
    """نمایش جزییات یک گزارش + Insights کامل"""
    report = get_object_or_404(Report, id=report_id)
    insights = report.insights
    # تبدیل insights به فرمت قابل نمایش در قالب
    kpis = insights.get('kpis', {})
    text_insights = insights.get('text_insights', [])
    top_products = insights.get('top_products', [])
    top_customers = insights.get('top_customers', [])
    # همچنین می‌توان mapping را نیز نمایش داد
    mapping = report.mapping
    context = {
        'report': report,
        'kpis': kpis,
        'text_insights': text_insights,
        'top_products': top_products,
        'top_customers': top_customers,
        'mapping': mapping,
    }
    return render(request, 'admin_panel/report_detail.html', context)

@staff_member_required
def delete_user(request, user_id):
    """حذف کاربر و تمام گزارش‌هایش (با تأیید)"""
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        user.delete()
        return redirect('admin_panel:user_list')
    return redirect('admin_panel:user_list')

@staff_member_required
def delete_report(request, report_id):
    """حذف یک گزارش (فایل)"""
    if request.method == 'POST':
        report = get_object_or_404(Report, id=report_id)
        report.delete()
        return redirect('admin_panel:report_list')
    return redirect('admin_panel:report_list')