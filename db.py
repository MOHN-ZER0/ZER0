import json
import os

class Database:
    def __init__(self, filename="database.json"):
        self.filename = filename
        self.data = self.load()

    def load(self):
        """تحميل جميع البيانات من الملف، وإذا لم يكن موجوداً يرجع قاموس فارغ"""
        if os.path.exists(self.filename):
            with open(self.filename, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        return {}

    def save(self):
        """حفظ البيانات فوراً في الملف لضمان عدم ضياع أي شيء"""
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    def get(self, key, default=None):
        """جلب أي بيانات مخزنة بناءً على المفتاح (مثل معرف السيرفر أو القسم)"""
        return self.data.get(str(key), default)

    def set(self, key, value):
        """حفظ أو تحديث أي بيانات جديدة وحفظها تلقائياً"""
        self.data[str(key)] = value
        self.save()

    def remove(self, key):
        """حذف أي بيانات لم تعد بحاجة إليها"""
        if str(key) in self.data:
            del self.data[str(key)]
            self.save()

# نسخة جاهزة للاستيراد في كل ملفات البوت
db = Database("database.json")
