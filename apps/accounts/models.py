from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = [
        ('ADMIN', 'Administrator'),
        ('STUDENT', 'Student'),
        ('DRIVER', 'Driver'),
        ('PARENT', 'Parent'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='STUDENT', db_index=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    def is_admin_role(self):
        return self.role == 'ADMIN' or self.is_superuser

    def is_student_role(self):
        return self.role == 'STUDENT'

    def is_driver_role(self):
        return self.role == 'DRIVER'

    def is_parent_role(self):
        return self.role == 'PARENT'

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    student_id = models.CharField(max_length=50, unique=True, db_index=True)
    department = models.CharField(max_length=100, default='Computer Science')
    academic_year = models.CharField(max_length=20, default='3rd Year')
    emergency_contact = models.CharField(max_length=20, blank=True, null=True)
    home_address = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.student_id} - {self.user.get_full_name()}"


class ParentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='parent_profile')
    relationship = models.CharField(max_length=50, default='Guardian')
    students = models.ManyToManyField(StudentProfile, related_name='parents', blank=True)

    def __str__(self):
        return f"Parent: {self.user.get_full_name()}"


class DriverProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='driver_profile')
    license_number = models.CharField(max_length=50, unique=True)
    experience_years = models.PositiveIntegerField(default=5)
    is_active_duty = models.BooleanField(default=True)

    def __str__(self):
        return f"Driver: {self.user.get_full_name()} ({self.license_number})"
