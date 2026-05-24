from django.db import models

from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    BaseUserManager,
)
from django.utils.html import format_html


from django.utils.html import format_html


# from django.core.validators import validate_email
from django.core.exceptions import ValidationError
# from django_softdelete.models import models.Model
import uuid


# DEPARTMENT_TYPE=(
#     ("مشکلا")
# )




from django.contrib.auth.models import BaseUserManager
from django.contrib.auth.password_validation import validate_password
# from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db.models.query import QuerySet


class UserManager(BaseUserManager):
    
    def create_user(
        self,
        email,
        password=None
    ):
        if not email:
            raise ValueError("email is required")

        if self.filter(email=self.normalize_email(email)).exists():
            raise ValidationError("email is already taken")

        try:
            # validate_email(email)
            user = self.model(email=self.normalize_email(email))
            user.set_password(password)
            user.save(using=self._db)
            return user

        except Exception as e:
            raise ValidationError(e)

    def create_superuser(self, phone_number, email, password=None):
        try:
            # validate_email(email)

            user = self.model(phone_number=phone_number, email=email)
            user.set_password(password)
            user.save(using=self._db)
            user.is_admin = True
            user.is_active = True
            user.is_staff = True
            user.is_superuser = True

            user.save(using=self._db)

            return user

        except Exception as e:
            raise ValidationError(e)

   

   


def upload_to_abr_profile_image(instance,filename):

    return f"{instance.user.phone}/{filename}"

class User(AbstractBaseUser,PermissionsMixin):
    
    id = models.UUIDField(
        verbose_name="ای دی کاربر",
        help_text="ای دی کاربر",
        unique=True,
        editable=False,
        default=uuid.uuid4,
        primary_key=True,
        db_index=True,
    )

    username = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="username",
        db_index=True,
        help_text="username را وارد کنید",
    )

    first_name = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="اسم",
        db_index=True,
        help_text="اسم را وارد کنید",
    )

    last_name = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="نام خوانوادگی",
        db_index=True,
        help_text="نام خوانوادگی را وارد کنید",
        
    )

    email = models.EmailField(
        max_length=100,
        verbose_name="ایمیل",
        help_text="ایمیل خود را وارد کنید",
        validators=[],
        db_index=True,
        null=True,
        blank=True,
        unique=True,

    )

    phone_number = models.CharField(
        max_length=11,
        # unique=True,
        verbose_name="شماره تلفن",
        null=True,
        blank=True,
        help_text="شماره تلفن خود راوارد کنید",
    )

    date_joined = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="تاریخ ساخنه شدن",
        help_text="تاریخ جوین شدن",
    )

    user_ip = models.GenericIPAddressField(
        db_index=True,
        blank=True,
        null=True,
        verbose_name="ای پی user",
        help_text="ای پی user",
    )

    last_login = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="تاریخ اخرین ورود",
        help_text=" اخرین زمان ورود",
    )

    is_admin = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="ادمین",
        help_text="کاربر ادمین هست ",
    )

    is_active = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="کاربر فعال",
        help_text="کاربر فعال هست",
    )

    is_staff = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="کاربر مدیر",
        help_text="کاربر مدیر هست",
    )

    is_superuser = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="کاربر سوپر یوزر",
        help_text=" کاربر سوپر یوزراست",
    )

    created = models.DateTimeField(
        auto_now_add=True,
        help_text="زمان ساخت",
        verbose_name="زمان ساخت",
        db_index=True,
        # TODO
        # must be deleted
        blank=True,
        null=True,
    )

    updated = models.DateTimeField(
        auto_now=True,
        help_text="زمان ارتقا",
        verbose_name="زمان ارتقا",
        db_index=True,
        # TODO
        # must be deleted
        blank=True,
        null=True,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["phone_number"]

    objects = UserManager()

    # def save(self, *args, **kwargs):
    #     if self.phone_number.startswith("0") and len(self.phone_number) == 11:
    #         return super().save(*args, **kwargs)
    #     raise ValidationError("phone number Value Must Be 11")

    def __str__(self) -> str:
        return "  شماره تلفن کاربر : "+str(self.phone_number)

    def has_perm(self, perm, obj=None):
        return self.is_admin

    def has_module_perms(self, add_label):
        return True



    class Meta(AbstractBaseUser.Meta):
        verbose_name = "کاربران"
        verbose_name_plural = "کاربران"
        ordering = ["created"]


class Report(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports')
    session_id = models.CharField(max_length=100, unique=True)
    filename = models.CharField(max_length=255)
    mapping = models.JSONField()
    insights = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reports"

    def __str__(self):
        return f"{self.filename} - {self.session_id}"