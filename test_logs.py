#!/usr/bin/env python
import os
import django

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Spenta.settings')
django.setup()

print("Django is working!")
print("If you see this, your Python environment is working")
