import subprocess
import time
import glob
from google.colab import files

print("1. Создаем обновленный main.py v2.7 с CoPET и TPU...")
with open("main.py", "w", encoding="utf-8") as f:
    f.write('''import os
import json
import ssl
import threading
from urllib import request, error
from kivy.app import App
from kivy.metrics import dp, sp
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.clock import mainthread
from kivy.utils import platform

CLOUD_SLICER_URL = "https://my-3d-slicer.onrender.com"
Window.clearcolor = (0.12, 0.13, 0.15, 1)

DEFAULT_SPOOL_PRICES = {
    "PLA": "800",
    "COPET": "700",
    "PETG": "700",
    "ABS": "650",
    "TPU": "1100"
}

def send_to_cloud(url, fields, file_data, file_name):
    boundary = '----AppMultipartBoundaryX79'
    body = bytearray()
    
    for k, v in fields.items():
        body.extend(f'--{boundary}\\r\\n'.encode('utf-8'))
        body.extend(f'Content-Disposition: form-data; name="{k}"\\r\\n\\r\\n'.encode('utf-8'))
        body.extend(f'{v}\\r\\n'.encode('utf-8'))
        
    body.extend(f'--{boundary}\\r\\n'.encode('utf-8'))
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{file_name}"\\r\\n'.encode('utf-8'))
    body.extend(b'Content-Type: application/sla\\r\\n\\r\\n')
    body.extend(file_data)
    body.extend(b'\\r\\n')
    body.extend(f'--{boundary}--\\r\\n'.encode('utf-8'))
    
    ctx = ssl._create_unverified_context()
    req = request.Request(f"{url}/slice", data=bytes(body))
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    req.add_header('User-Agent', 'Mozilla/5.0') 
    
    with request.urlopen(req, timeout=120, context=ctx) as resp:
        return json.loads(resp.read().decode('utf-8'))

class Calc3DApp(App):
    def build(self):
        self.title = "3D Print Calc"
        self.last_file_bytes = None
        self.last_file_name = None
        self.current_material = "PLA"

        if platform == 'android':
            from android import activity
            activity.bind(on_activity_result=self.on_activity_result)

        root = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        main_layout = BoxLayout(
            orientation='vertical',
            padding=[dp(14), dp(14), dp(14), dp(20)],
            spacing=dp(9),
            size_hint_y=None
        )
        main_layout.bind(minimum_height=main_layout.setter('height'))

        main_layout.add_widget(Label(
            text="3D PRINT CALCULATOR",
            font_size=sp(20),
            bold=True,
            size_hint_y=None,
            height=dp(34),
            color=(0.25, 0.72, 1.0, 1)
        ))

        btn_file = Button(
            text="📁 1. ВЫБРАТЬ STL ФАЙЛ",
            font_size=sp(15),
            bold=True,
            size_hint_y=None,
            height=dp(46),
            background_normal='',
            background_color=(0.18, 0.38, 0.65, 1)
        )
        btn_file.bind(on_release=self.open_native_picker)
        main_layout.add_widget(btn_file)

        self.lbl_stl_info = Label(
            text="Файл не выбран",
            font_size=sp(13),
            size_hint_y=None,
            height=dp(24),
            color=(0.7, 0.7, 0.7, 1)
        )
        main_layout.add_widget(self.lbl_stl_info)

        # Выбор пластика кнопками (5 материалов)
        mat_box = BoxLayout(orientation='horizontal', spacing=dp(5), size_hint_y=None, height=dp(38))
        self.mat_buttons = {}
        materials = ["PLA", "CoPET", "PETG", "ABS", "TPU"]

        for mat in materials:
            b = Button(
                text=mat,
                bold=True,
                font_size=sp(12),
                background_normal='',
                background_color=(0.2, 0.55, 0.9, 1) if mat == "PLA" else (0.25, 0.28, 0.32, 1)
            )
            b.bind(on_release=lambda btn, m=mat: self.select_material(m))
            self.mat_buttons[mat] = b
            mat_box.add_widget(b)

        main_layout.add_widget(mat_box)

        grid = GridLayout(cols=2, spacing=[dp(10), dp(6)], size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))

        grid.add_widget(self._create_label("Стенки (периметры):"))
        self.in_walls = self._create_input("2")
        grid.add_widget(self.in_walls)

        grid.add_widget(self._create_label("Заполнение (%):"))
        self.in_infill = self._create_input("15")
        grid.add_widget(self.in_infill)

        grid.add_widget(self._create_label("Катушка 1 кг (грн):"))
        self.in_spool_cost = self._create_input("800")
        grid.add_widget(self.in_spool_cost)

        grid.add_widget(self._create_label("Станок + свет (грн/ч):"))
        self.in_hourly_rate = self._create_input("40")
        grid.add_widget(self.in_hourly_rate)

        grid.add_widget(self._create_label("Маржа / Наценка (x):"))
        self.in_markup = self._create_input("2.0")
        grid.add_widget(self.in_markup)

        grid.add_widget(self._create_label("Вес детали (г):"))
        self.in_weight = self._create_input("0.0")
        grid.add_widget(self.in_weight)

        grid.add_widget(self._create_label("Время печати (ч):"))
        self.in_time = self._create_input("0.0")
        grid.add_widget(self.in_time)

        # Автопересчет при ручной правке цифр
        self.in_weight.bind(text=self.calculate)
        self.in_time.bind(text=self.calculate)
        self.in_spool_cost.bind(text=self.calculate)
        self.in_hourly_rate.bind(text=self.calculate)
        self.in_markup.bind(text=self.calculate)

        main_layout.add_widget(grid)

        self.btn_run = Button(
            text="🚀 2. НАРЕЗАТЬ И РАССЧИТАТЬ",
            font_size=sp(16),
            bold=True,
            size_hint_y=None,
            height=dp(52),
            background_normal='',
            background_color=(0.15, 0.68, 0.45, 1)
        )
        self.btn_run.bind(on_release=self.start_slice)
        main_layout.add_widget(self.btn_run)

        self.lbl_result = Label(
            text="Выберите файл, укажите пластик и нажмите расчет",
            font_size=sp(14),
            size_hint_y=None,
            height=dp(100),
            halign='center',
            valign='middle',
            color=(1, 1, 1, 1)
        )
        self.lbl_result.bind(size=self.lbl_result.setter('text_size'))
        main_layout.add_widget(self.lbl_result)

        root.add_widget(main_layout)
        return root

    def select_material(self, mat):
        self.current_material = mat
        inactive = (0.25, 0.28, 0.32, 1)
        active = (0.2, 0.55, 0.9, 1)
        
        for name, btn in self.mat_buttons.items():
            btn.background_color = active if name == mat else inactive

        # Подставляем стандартную цену за катушку
        mat_key = mat.upper()
        if mat_key in DEFAULT_SPOOL_PRICES:
            self.in_spool_cost.text = DEFAULT_SPOOL_PRICES[mat_key]
            
        self.calculate()

    def _create_label(self, text):
        lbl = Label(
            text=text, font_size=sp(13), size_hint_y=None, height=dp(38),
            halign='left', valign='middle', color=(0.85, 0.88, 0.9, 1)
        )
        lbl.bind(size=lbl.setter('text_size'))
        return lbl

    def _create_input(self, default_val):
        return TextInput(
            text=default_val, multiline=False, input_filter='float',
            font_size=sp(15), size_hint_y=None, height=dp(38),
            padding=[dp(8), dp(8), dp(8), dp(8)]
        )

    def open_native_picker(self, instance):
        if platform != 'android':
            self.lbl_stl_info.text = "Выбор доступен на смартфоне"
            return
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        Intent = autoclass('android.content.Intent')
        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType("*/*")
        PythonActivity.mActivity.startActivityForResult(intent, 0x101)

    def on_activity_result(self, request_code, result_code, intent_data):
        if request_code != 0x101: return
        from jnius import autoclass
        Activity = autoclass('android.app.Activity')
        if result_code != Activity.RESULT_OK or intent_data is None: return

        uri = intent_data.getData()
        if not uri: return

        try:
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            content_resolver = PythonActivity.mActivity.getContentResolver()
            
            file_name = "model.stl"
            cursor = content_resolver.query(uri, None, None, None, None)
            if cursor and cursor.moveToFirst():
                idx = cursor.getColumnIndex("_display_name")
                if idx != -1: file_name = cursor.getString(idx)
            if cursor: cursor.close()

            stream = content_resolver.openInputStream(uri)
            chunks = []
            buf = bytearray(65536)
            while True:
                r = stream.read(buf)
                if r == -1: break
                chunks.append(bytes(buf[:r]))
            stream.close()

            self.last_file_bytes = bytes(b''.join(chunks))
            self.last_file_name = file_name
            self.lbl_stl_info.text = f"Загружен: {file_name[:22]}"
            self.lbl_stl_info.color = (0.3, 0.8, 1.0, 1)

        except Exception as e:
            self.lbl_stl_info.text = "Ошибка чтения файла"
            self.lbl_stl_info.color = (0.9, 0.3, 0.3, 1)

    def start_slice(self, instance):
        if not self.last_file_bytes:
            self.lbl_stl_info.text = "Сначала выберите STL файл!"
            self.lbl_stl_info.color = (1.0, 0.4, 0.4, 1)
            return

        self.btn_run.disabled = True
        self.lbl_stl_info.text = f"⏳ Нарезка ({self.current_material})..."
        self.lbl_stl_info.color = (1.0, 0.75, 0.2, 1)
        threading.Thread(target=self.thread_upload_and_slice).start()

    def thread_upload_and_slice(self):
        fields = {
            "perimeters": self.in_walls.text.strip(),
            "infill": self.in_infill.text.strip(),
            "material": self.current_material.upper()
        }
        try:
            res = send_to_cloud(CLOUD_SLICER_URL, fields, self.last_file_bytes, self.last_file_name)
            if res.get("status") == "success":
                self.on_slice_success(res.get("weight_g", 0.0), res.get("time_hours", 0.0))
            else:
                self.on_slice_error(res.get("message", "Сбой слайсера"))
        except error.URLError as e:
            self.on_slice_error(f"Сбой сети: {e.reason}")
        except Exception as e:
            self.on_slice_error("Нет связи со слайсером")

    @mainthread
    def on_slice_success(self, weight, time_h):
        self.btn_run.disabled = False
        self.lbl_stl_info.text = f"✓ {self.last_file_name[:15]} нарезан ({self.current_material})!"
        self.lbl_stl_info.color = (0.3, 0.9, 0.4, 1)
        self.in_weight.text = f"{weight:.1f}"
        self.in_time.text = f"{time_h:.2f}"
        self.calculate()

    @mainthread
    def on_slice_error(self, err_msg):
        self.btn_run.disabled = False
        self.lbl_stl_info.text = f"Ошибка: {str(err_msg)[:30]}"
        self.lbl_stl_info.color = (0.9, 0.3, 0.3, 1)

    def calculate(self, *args):
        try:
            w_str = self.in_weight.text.strip()
            t_str = self.in_time.text.strip()
            s_str = self.in_spool_cost.text.strip()
            h_str = self.in_hourly_rate.text.strip()
            m_str = self.in_markup.text.strip()

            if not (w_str and t_str and s_str and h_str and m_str):
                return

            w = float(w_str)
            t = float(t_str)
            s = float(s_str)
            h = float(h_str)
            m = float(m_str)

            c_plast = (s / 1000.0) * w
            c_mach = h * t
            base = c_plast + c_mach
            total = base * m

            self.lbl_result.text = (
                f"[color=3bf08b][b]ИТОГО К ОПЛАТЕ: {total:.2f} грн[/b][/color]\\n"
                f"Себестоимость: {base:.2f} грн\\n"
                f"• Пластик {self.current_material} ({w}г): {c_plast:.2f} грн\\n"
                f"• Станок ({t}ч): {c_mach:.2f} грн"
            )
            self.lbl_result.markup = True
        except:
            pass

if __name__ == '__main__':
    Calc3DApp().run()
''')

print("2. Меняем версию на 2.7...")
!sed -i 's/version = .*/version = 2.7/g' buildozer.spec
!rm -rf bin/*

print("3. Сборка APK v2.7...")
process = subprocess.Popen(
    "export PIP_ONLY_BINARY=none; yes | buildozer -v android debug > build.log 2>&1",
    shell=True,
    executable="/bin/bash"
)

start_time = time.time()
while process.poll() is None:
    elapsed = int(time.time() - start_time) // 60
    print(f"... сборка в процессе ({elapsed} мин.)")
    time.sleep(15)

apk_list = glob.glob('bin/*.apk')
if apk_list:
    print(f"\n🎉 ГОТОВО! Скачиваем v2.7: {apk_list[0]}")
    files.download(apk_list[0])
else:
    print("\nОшибка сборки:")
    !tail -n 30 build.log
