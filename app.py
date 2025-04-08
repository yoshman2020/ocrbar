import copy
import csv
import sqlite3
import tkinter as tk
from tkinter import filedialog, ttk

import cv2
import pyocr
import pyzbar.pyzbar as pyzbar
from PIL import Image, ImageDraw, ImageFont, ImageTk


class Rectangle:
    def __init__(self, left=0, top=0, right=0, bottom=0):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom

    def __str__(self):
        return (
            f"Rectangle(left={self.left}, top={self.top}, "
            + f"right={self.right}, bottom={self.bottom})"
        )

    def width(self):
        return self.right - self.left

    def height(self):
        return self.bottom - self.top

    def area(self):
        return self.width() * self.height()

    def perimeter(self):
        return 2 * (self.width() + self.height())

    def contains(self, x, y):
        return (
            self.left <= x < self.right and self.top <= y < self.y + self.bottom
        )


class CameraApp:

    CANVAS_WIDTH = 640
    CANVAS_HEIGHT = 480

    DB_NAME = "app.db"

    window_closed = False
    camera_on = False
    current_x = CANVAS_WIDTH
    current_y = CANVAS_HEIGHT

    rect_start_x = 0
    rect_start_y = 0
    rect_id = 0
    rect = Rectangle(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)

    rect_range = Rectangle(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)

    def __init__(self, window):
        self.create_widgets(window)

        self.find_camera()

        self.load_db()

        self.cap = cv2.VideoCapture(int(self.cmb_camera.get()))
        self.window.protocol("WM_DELETE_WINDOW", self.close_window)

        tools = pyocr.get_available_tools()
        self.tool = tools[0]

        self.rect_id = self.canvas.create_rectangle(
            0, 0, self.CANVAS_WIDTH, self.CANVAS_HEIGHT, outline="red"
        )

        self.camera_on = True
        self.show_feed()

    def create_widgets(self, window):
        self.window = window
        self.window.title("OCR")

        self.canvas = tk.Canvas(
            self.window, width=self.CANVAS_WIDTH, height=self.CANVAS_HEIGHT
        )
        self.canvas.grid(row=0, column=0)
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)

        self.frm_buttons = tk.Frame(self.window)
        self.frm_buttons.grid(row=0, column=1)

        self.frm_select_camera = tk.Frame(self.frm_buttons)
        self.frm_select_camera.pack(pady=10)

        self.lbl_camera = tk.Label(self.frm_select_camera, text="カメラID")
        self.lbl_camera.pack(side=tk.LEFT)

        self.cmb_camera = ttk.Combobox(
            self.frm_select_camera, state="readonly", width=5
        )
        self.cmb_camera.bind("<<ComboboxSelected>>", self.cmb_camera_changed)
        self.cmb_camera.pack(side=tk.LEFT)

        style = ttk.Style()
        STYLE_BTN_TBUTTON = "BTN.TButton"
        style.configure(
            STYLE_BTN_TBUTTON,
            font=("MS Gothic", 24),
            width=10,
            padx=10,
            pady=10,
        )

        self.btn_select = ttk.Button(
            self.frm_buttons,
            text="範囲選択",
            command=self.btn_select_clicked,
            style=STYLE_BTN_TBUTTON,
        )
        self.btn_select.pack(pady=10)

        self.btn_clear = ttk.Button(
            self.frm_buttons,
            text="クリア",
            command=self.btn_clear_clicked,
            style=STYLE_BTN_TBUTTON,
        )
        self.btn_clear.pack(pady=10)

        self.btn_ok = ttk.Button(
            self.frm_buttons,
            text="確定",
            command=self.btn_ok_clicked,
            style=STYLE_BTN_TBUTTON,
        )
        self.btn_ok.pack(pady=10)

        self.btn_cancel = ttk.Button(
            self.frm_buttons,
            text="キャンセル",
            command=self.btn_cancel_clicked,
            style=STYLE_BTN_TBUTTON,
        )
        self.btn_cancel.pack(pady=10)

        self.btn_read = ttk.Button(
            self.frm_buttons,
            text="CSV読込み",
            command=self.btn_read_clicked,
            style=STYLE_BTN_TBUTTON,
        )
        self.btn_read.pack(pady=10)

        self.frm_list = tk.Frame(self.frm_buttons)
        self.frm_list.pack(pady=10)

        self.lst_csv = tk.Listbox(self.frm_list)
        self.lst_csv.grid(row=0, column=0)

        self.xbar = ttk.Scrollbar(
            self.frm_list, orient="horizontal", command=self.lst_csv.xview
        )
        self.lst_csv["xscrollcommand"] = self.xbar.set
        self.xbar.grid(row=1, column=0, sticky="ew")

        self.ybar = ttk.Scrollbar(
            self.frm_list, orient="vertical", command=self.lst_csv.yview
        )
        self.lst_csv["yscrollcommand"] = self.ybar.set
        self.ybar.grid(row=0, column=1, sticky="ns")

        self.btn_add = ttk.Button(
            self.frm_buttons,
            text="追加",
            command=self.btn_add_clicked,
            style=STYLE_BTN_TBUTTON,
        )
        self.btn_add.pack(pady=10)

        self.btn_delete = ttk.Button(
            self.frm_buttons,
            text="削除",
            command=self.btn_delete_clicked,
            style=STYLE_BTN_TBUTTON,
        )
        self.btn_delete.pack(pady=10)

    def close_window(self):
        self.cap.release()
        cv2.destroyAllWindows()
        self.window_closed = True
        self.window.quit()
        self.window.destroy()

    def find_camera(self):
        camera_ids = []
        for i in range(10):
            try:
                cap = cv2.VideoCapture(i)
                if cap is None or not cap.isOpened():
                    break
            except cv2.error:
                break
            camera_ids.append(i)

        self.cmb_camera["values"] = camera_ids
        if len(camera_ids) > 0:
            self.cmb_camera.current(0)

    def cmb_camera_changed(self, event):
        if self.cap:
            self.cap.release()
        self.cap = cv2.VideoCapture(int(self.cmb_camera.get()))

    def show_feed(self):
        ret, frame = self.cap.read()
        if not ret:
            return

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)

        barcodes = pyzbar.decode(frame_rgb)
        barcode_info = None

        for barcode in barcodes:
            x, y, w, h = barcode.rect
            barcode_info = barcode.data.decode("utf-8")
            cv2.rectangle(frame_rgb, (x, y), (x + w, y + h), (0, 255, 0), 2)
            break

        img_range = img.crop(
            (
                self.rect_range.left,
                self.rect_range.top,
                self.rect_range.right,
                self.rect_range.bottom,
            )
        )

        builder = pyocr.builders.TextBuilder()
        result = self.tool.image_to_string(
            img_range, lang="jpn", builder=builder
        )

        if barcode_info:
            cv2.putText(
                frame_rgb,
                barcode_info,
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2,
            )
            img = Image.fromarray(frame_rgb)

        if result:
            font_path = r"C:\Windows\Fonts\msgothic.ttc"
            font = ImageFont.truetype(font_path, 24)
            draw = ImageDraw.Draw(img)
            draw.text(
                (self.rect.left, self.rect.top),
                result,
                font=font,
                fill=(0, 255, 0, 0),
            )

            if barcode_info:
                bar_string = self.get_bar_string(barcode_info)
                if bar_string:
                    color = (
                        (0, 0, 255, 0)
                        if bar_string[0] == result
                        else (255, 0, 0, 0)
                    )
                    draw.text((0, 0), bar_string[0], font=font, fill=color)

        self.img_tk = ImageTk.PhotoImage(image=img)

        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.img_tk)

        self.canvas.delete(self.rect_id)

        self.rect_id = self.canvas.create_rectangle(
            self.rect.left,
            self.rect.top,
            self.rect.right,
            self.rect.bottom,
            outline="red",
        )

        if self.camera_on:
            self.window.after(100, self.show_feed)

    def btn_select_clicked(self):
        self.camera_on = False

    def start_drag(self, event):
        if self.camera_on:
            return
        if (
            0 <= event.x <= self.CANVAS_WIDTH
            and 0 <= event.y <= self.CANVAS_HEIGHT
        ):
            self.rect_start_x = event.x
            self.rect_start_y = event.y

    def drag(self, event):
        if self.camera_on:
            return
        if (
            0 <= event.x <= self.CANVAS_WIDTH
            and 0 <= event.y <= self.CANVAS_HEIGHT
        ):
            self.canvas.coords(
                self.rect_id,
                min(self.rect_start_x, event.x),
                min(self.rect_start_y, event.y),
                max(self.rect_start_x, event.x),
                max(self.rect_start_y, event.y),
            )
            self.rect.left = min(self.rect_start_x, event.x)
            self.rect.top = min(self.rect_start_y, event.y)
            self.rect.right = max(self.rect_start_x, event.x)
            self.rect.bottom = max(self.rect_start_y, event.y)

    def btn_clear_clicked(self):
        if self.camera_on:
            return
        self.canvas.coords(
            self.rect_id, 0, 0, self.CANVAS_WIDTH, self.CANVAS_HEIGHT
        )
        self.rect.left = 0
        self.rect.top = 0
        self.rect.right = self.CANVAS_WIDTH
        self.rect.bottom = self.CANVAS_HEIGHT

    def btn_ok_clicked(self):
        self.rect_range = copy.deepcopy(self.rect)
        self.camera_on = True
        self.show_feed()

    def btn_cancel_clicked(self):
        self.rect = copy.deepcopy(self.rect_range)
        self.camera_on = True
        self.show_feed()

    def btn_read_clicked(self):
        csv_path = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv")]
        )
        with open(csv_path, "r") as fin:
            dr = csv.DictReader(fin)
            to_db = [tuple(i[f].rstrip() for f in dr.fieldnames) for i in dr]

        self.save_db(to_db)

        self.load_db()

    def save_db(self, to_db):
        # 更新用に2列目を追加
        to_db_add = [(*i, i[1]) for i in to_db]
        con = sqlite3.connect(self.DB_NAME)
        cur = con.cursor()
        cur.executemany(
            "INSERT INTO data (barcode, string) VALUES (?, ?)"
            + " ON CONFLICT(barcode) DO UPDATE SET string = ?;",
            to_db_add,
        )
        con.commit()
        con.close()

    def load_db(self):
        con = sqlite3.connect(self.DB_NAME)
        cur = con.cursor()
        cur.execute("SELECT * FROM data;")
        data = cur.fetchall()
        con.close()

        self.lst_csv.delete(0, tk.END)
        for item in data:
            self.lst_csv.insert(tk.END, f"{item[0]} - {item[1]}")

    def get_bar_string(self, barcode):
        con = sqlite3.connect(self.DB_NAME)
        cur = con.cursor()
        cur.execute("SELECT string FROM data WHERE barcode = ?;", (barcode,))
        data = cur.fetchone()
        con.close()

        if data:
            return data
        else:
            return ""

    def btn_add_clicked(self):
        dialog = CustomDialog(self.window)
        if dialog.barcode != "":
            self.save_db([(dialog.barcode, dialog.bar_string)])
            self.load_db()

    def btn_delete_clicked(self):
        index = self.lst_csv.curselection()
        if index:
            barcode = self.lst_csv.get(index).split(" - ")[0]
            con = sqlite3.connect(self.DB_NAME)
            cur = con.cursor()
            cur.execute(
                "DELETE FROM data WHERE barcode = ?;",
                (barcode,),
            )
            con.commit()
            con.close()
            self.load_db()


class CustomDialog(tk.simpledialog.Dialog):

    def __init__(self, parent):
        self.barcode = ""
        self.bar_string = ""
        super(CustomDialog, self).__init__(parent=parent, title="追加")

    def body(self, parent):
        lbl_barcode = tk.Label(parent, text="barcode", width=6)
        lbl_barcode.grid(row=0, column=0)

        self.ent_barcode = tk.Entry(parent)
        self.ent_barcode.grid(row=0, column=1)

        lbl_bar_string = tk.Label(parent, text="文字", width=6)
        lbl_bar_string.grid(row=1, column=0)

        self.end_bar_string = tk.Entry(parent)
        self.end_bar_string.grid(row=1, column=1)

        return self.ent_barcode

    def apply(self):
        self.barcode = self.ent_barcode.get()
        self.bar_string = self.end_bar_string.get()


def main():
    root = tk.Tk()
    _ = CameraApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
