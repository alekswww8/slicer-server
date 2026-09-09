import os
import re
import gc
import math
import tempfile
import subprocess
from fastapi import FastAPI, UploadFile, File, Form, Response

os.environ["MALLOC_ARENA_MAX"] = "2"

app = FastAPI()

DENSITIES = {
    "PLA": 1.24,
    "COPET": 1.27,
    "PETG": 1.27,
    "ABS": 1.04,
    "TPU": 1.21
}

BASE_CONFIG = """
layer_height = 0.28
first_layer_height = 0.28
nozzle_diameter = 0.4
filament_diameter = 1.75
threads = 1
fill_pattern = rectilinear
solid_fill_pattern = rectilinear
top_solid_layers = 3
bottom_solid_layers = 3
gap_fill_enabled = 1
gap_fill_speed = 40
infill_overlap = 25%
bridge_flow_ratio = 1
cooling = 0
disable_fan_first_layers = 1
"""

def parse_gcode_stats(gcode_path: str, material: str):
    weight_g = 0.0
    time_seconds = 0
    density = DENSITIES.get(material.upper(), 1.24)

    with open(gcode_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

        m_weight = re.search(r';\s*filament used \[g\]\s*=\s*([0-9.]+)', content)
        if m_weight and float(m_weight.group(1)) > 0:
            weight_g = float(m_weight.group(1))
        else:
            m_cm3 = re.search(r';\s*filament used \[cm3\]\s*=\s*([0-9.]+)', content)
            if m_cm3 and float(m_cm3.group(1)) > 0:
                weight_g = float(m_cm3.group(1)) * density
            else:
                m_mm = re.search(r';\s*filament used \[mm\]\s*=\s*([0-9.]+)', content)
                m_m = re.search(r';\s*filament used\s*=\s*([0-9.]+)m', content)
                
                length_mm = 0.0
                if m_mm:
                    length_mm = float(m_mm.group(1))
                elif m_m:
                    length_mm = float(m_mm.group(1)) * 1000.0

                if length_mm > 0:
                    volume_cm3 = (math.pi * (0.875 ** 2) * length_mm) / 1000.0
                    weight_g = volume_cm3 * density

        m_time = re.search(r';\s*estimated printing time \(normal mode\)\s*=\s*(.+)', content)
        if m_time:
            time_str = m_time.group(1).strip()
            days = re.search(r'(\d+)d', time_str)
            hours = re.search(r'(\d+)h', time_str)
            minutes = re.search(r'(\d+)m', time_str)
            d = int(days.group(1)) if days else 0
            h = int(hours.group(1)) if hours else 0
            m = int(minutes.group(1)) if minutes else 0
            time_seconds = d * 86400 + h * 3600 + m * 60

    return round(weight_g, 1), round(time_seconds / 3600.0, 2)

# РАЗРЕШАЕМ И GET, И HEAD — ТЕПЕРЬ RENDER НЕ БУДЕТ УБИВАТЬ СЕРВЕР
@app.api_route("/", methods=["GET", "HEAD"])
def health_check():
    return {"status": "ok", "message": "3D Slicer Server is running"}

@app.post("/slice")
async def slice_stl(
    file: UploadFile = File(...),
    infill: int = Form(15),
    perimeters: int = Form(2),
    material: str = Form("PLA"),
    is_vase: bool = Form(False)
):
    with tempfile.TemporaryDirectory() as tmpdir:
        input_stl = os.path.join(tmpdir, "model.stl")
        output_gcode = os.path.join(tmpdir, "model.gcode")
        config_ini = os.path.join(tmpdir, "config.ini")

        valid_infill = max(0, min(100, infill))
        valid_perimeters = max(1, min(20, perimeters))

        with open(config_ini, "w") as cfg:
            cfg.write(BASE_CONFIG.strip() + "\n")
            if is_vase:
                cfg.write("spiral_vase = 1\nperimeters = 1\nfill_density = 0%\ntop_solid_layers = 0\n")
            else:
                cfg.write(f"perimeters = {valid_perimeters}\n")
                cfg.write(f"fill_density = {valid_infill}%\n")

        content = await file.read()
        with open(input_stl, "wb") as f:
            f.write(content)
        del content
        gc.collect()

        cmd = [
            "prusa-slicer",
            "--export-gcode",
            "--load", config_ini,
            "--output", output_gcode,
            input_stl
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Превышено время ожидания"}

        if not os.path.exists(output_gcode):
            err_log = res.stderr.decode('utf-8', errors='ignore').strip()
            last_err = err_log.split("\n")[-1] if err_log else "Сбой нарезки"
            return {"status": "error", "message": f"{last_err[:40]}"}

        weight_g, time_h = parse_gcode_stats(output_gcode, material)
        gc.collect()

        return {"status": "success", "weight_g": weight_g, "time_hours": time_h}
