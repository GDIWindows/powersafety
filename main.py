#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
电力安全题库 - 完整版
功能：自动下载题库、OCR识别（拍照+图片）、本地缓存、收藏功能
"""

import os
import sys
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime

# ==================== 强制设置字体 ====================
from kivy.config import Config
Config.set('kivy', 'default_font', [
    'C:/Windows/Fonts/simsun.ttc',
    'C:/Windows/Fonts/msyh.ttc',
])

# ==================== 导入Kivy ====================
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.graphics import Color, RoundedRectangle
from kivy.network.urlrequest import UrlRequest
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image as KivyImage
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.progressbar import ProgressBar
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.utils import platform

# ==================== 注册中文字体 ====================
LabelBase.register(name='SimSun', fn_regular='C:/Windows/Fonts/simsun.ttc')
LabelBase.register(name='YaHei', fn_regular='C:/Windows/Fonts/msyh.ttc')
Config.set('kivy', 'default_font', ['SimSun', 'YaHei'])

# ==================== OCR功能 ====================
try:
    import pytesseract
    from PIL import Image, ImageEnhance
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    pytesseract = None
    Image = None

# ==================== 摄像头功能 ====================
try:
    from kivy.garden.xcamera import XCamera
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False
    XCamera = None

# ==================== 服务器地址 ====================
SERVER_URL = "http://dgtm.gwindowsdns.dpdns.org/questions.xml"
CACHE_FILE = "questions_cache.xml"
FAVORITES_FILE = "favorites.json"

# ==================== 数据模型 ====================
class Question:
    def __init__(self, qid, question, options, answer, explanation):
        self.id = qid
        self.question = question
        self.options = options
        self.answer = answer
        self.explanation = explanation


# ==================== 收藏管理 ====================
class FavoriteManager:
    def __init__(self):
        self.favorites = set()
        self.load()
    
    def load(self):
        """加载收藏列表"""
        if os.path.exists(FAVORITES_FILE):
            try:
                with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.favorites = set(data.get('favorites', []))
            except:
                self.favorites = set()
    
    def save(self):
        """保存收藏列表"""
        try:
            with open(FAVORITES_FILE, 'w', encoding='utf-8') as f:
                json.dump({'favorites': list(self.favorites)}, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def toggle(self, qid):
        """切换收藏状态"""
        qid = str(qid)
        if qid in self.favorites:
            self.favorites.remove(qid)
        else:
            self.favorites.add(qid)
        self.save()
        return qid in self.favorites
    
    def is_favorite(self, qid):
        """检查是否已收藏"""
        return str(qid) in self.favorites
    
    def get_all(self):
        """获取所有收藏ID"""
        return list(self.favorites)


# ==================== 题目卡片 ====================
class QuestionCard(BoxLayout):
    def __init__(self, question, app_instance, **kwargs):
        super().__init__(**kwargs)
        self.question = question
        self.app = app_instance
        self.orientation = 'vertical'
        self.size_hint_y = None
        self.height = 150
        self.padding = [12, 10, 12, 10]
        self.spacing = 4

        with self.canvas.before:
            Color(0.95, 0.97, 0.99, 1)
            self.bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[8])
        self.bind(pos=self.update_bg, size=self.update_bg)

        # 第一行：题号 + 收藏按钮
        top_row = BoxLayout(size_hint_y=None, height=35, spacing=8)
        
        # 题目标题
        q_text = f"[b]{question.id}.[/b] {question.question[:80]}"
        if len(question.question) > 80:
            q_text += '...'
        
        self.q_label = Label(
            text=q_text,
            markup=True,
            font_name='SimSun',
            font_size='15sp',
            color=(0.1, 0.15, 0.25, 1),
            halign='left',
            valign='middle',
            size_hint_x=0.85
        )
        top_row.add_widget(self.q_label)
        
        # 收藏按钮
        is_fav = self.app.fav_manager.is_favorite(question.id)
        self.fav_btn = Button(
            text='⭐' if is_fav else '☆',
            font_name='SimSun',
            font_size='20sp',
            size_hint_x=None,
            width=45,
            background_color=(1, 0.8, 0, 1) if is_fav else (0.8, 0.8, 0.8, 1),
            color=(0, 0, 0, 1)
        )
        self.fav_btn.bind(on_press=self.toggle_favorite)
        top_row.add_widget(self.fav_btn)
        
        self.add_widget(top_row)

        # 选项摘要
        opt_text = '  '.join(question.options[:3])
        if len(question.options) > 3:
            opt_text += ' ...'
        
        self.opt_label = Label(
            text=opt_text,
            font_name='SimSun',
            font_size='13sp',
            size_hint_y=None,
            height=25,
            color=(0.3, 0.4, 0.5, 1),
            halign='left',
            valign='middle'
        )
        self.add_widget(self.opt_label)

        # 答案和解析
        ans_text = f"答案: {question.answer}"
        if question.explanation:
            ans_text += f"  |  解析: {question.explanation[:40]}..."
        
        self.ans_label = Label(
            text=ans_text,
            font_name='SimSun',
            font_size='12sp',
            size_hint_y=None,
            height=25,
            color=(0.2, 0.4, 0.2, 1),
            halign='left',
            valign='middle'
        )
        self.add_widget(self.ans_label)

        # 点击事件（查看详情）
        self.bind(on_touch_down=self.show_detail)

    def update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size

    def toggle_favorite(self, instance):
        """切换收藏状态"""
        is_fav = self.app.fav_manager.toggle(self.question.id)
        self.fav_btn.text = '⭐' if is_fav else '☆'
        self.fav_btn.background_color = (1, 0.8, 0, 1) if is_fav else (0.8, 0.8, 0.8, 1)
        self.app.update_favorite_count()

    def show_detail(self, instance, touch):
        if not self.collide_point(touch.x, touch.y):
            return
        # 如果点击的是收藏按钮，不触发详情
        if self.fav_btn.collide_point(touch.x - self.fav_btn.x, touch.y - self.fav_btn.y):
            return

        content = BoxLayout(orientation='vertical', spacing=8, padding=16)
        q = self.question

        # 标题行（带收藏状态）
        title_row = BoxLayout(size_hint_y=None, height=40, spacing=8)
        title_row.add_widget(Label(
            text=f"[b]题目 {q.id}[/b]",
            markup=True,
            font_name='SimSun',
            font_size='18sp',
            color=(0.1, 0.2, 0.4, 1)
        ))
        fav_status = '⭐ 已收藏' if self.app.fav_manager.is_favorite(q.id) else '☆ 未收藏'
        title_row.add_widget(Label(
            text=fav_status,
            font_name='SimSun',
            font_size='14sp',
            size_hint_x=None,
            width=100,
            color=(1, 0.8, 0, 1) if self.app.fav_manager.is_favorite(q.id) else (0.5, 0.5, 0.5, 1)
        ))
        content.add_widget(title_row)
        
        # 题目正文
        content.add_widget(Label(
            text=q.question,
            font_name='SimSun',
            font_size='16sp',
            size_hint_y=None,
            height=80,
            text_size=(400, None)
        ))

        # 选项
        opt_text = '\n'.join(q.options)
        content.add_widget(Label(
            text=opt_text,
            font_name='SimSun',
            font_size='14sp',
            size_hint_y=None,
            height=120,
            text_size=(400, None)
        ))

        # 答案
        content.add_widget(Label(
            text=f"[b]答案:[/b] {q.answer}",
            markup=True,
            font_name='SimSun',
            size_hint_y=None,
            height=35,
            color=(0, 0.6, 0, 1)
        ))

        # 解析
        if q.explanation:
            content.add_widget(Label(
                text=f"[b]解析:[/b]\n{q.explanation}",
                markup=True,
                font_name='SimSun',
                font_size='13sp',
                size_hint_y=None,
                height=120,
                text_size=(400, None)
            ))

        # 底部按钮
        btn_row = BoxLayout(size_hint_y=None, height=44, spacing=12)
        
        close_btn = Button(
            text='关闭',
            font_name='SimSun',
            background_color=(0.3, 0.5, 0.8, 1)
        )
        
        fav_toggle_btn = Button(
            text='⭐ 取消收藏' if self.app.fav_manager.is_favorite(q.id) else '☆ 收藏本题',
            font_name='SimSun',
            background_color=(1, 0.8, 0, 0.8) if self.app.fav_manager.is_favorite(q.id) else (0.8, 0.8, 0.8, 0.8)
        )
        
        btn_row.add_widget(fav_toggle_btn)
        btn_row.add_widget(close_btn)
        content.add_widget(btn_row)

        popup = Popup(
            title='题目详情',
            content=content,
            size_hint=(0.9, 0.85),
            auto_dismiss=True
        )
        
        def on_close(inst):
            popup.dismiss()
        
        def on_toggle_fav(inst):
            is_fav = self.app.fav_manager.toggle(q.id)
            fav_toggle_btn.text = '⭐ 取消收藏' if is_fav else '☆ 收藏本题'
            fav_toggle_btn.background_color = (1, 0.8, 0, 0.8) if is_fav else (0.8, 0.8, 0.8, 0.8)
            # 更新卡片上的收藏按钮
            self.fav_btn.text = '⭐' if is_fav else '☆'
            self.fav_btn.background_color = (1, 0.8, 0, 1) if is_fav else (0.8, 0.8, 0.8, 1)
            self.app.update_favorite_count()
            # 如果当前在收藏列表，刷新
            if hasattr(self.app, 'current_tab') and self.app.current_tab == 'favorites':
                self.app.refresh_favorites()
        
        close_btn.bind(on_press=on_close)
        fav_toggle_btn.bind(on_press=on_toggle_fav)
        popup.open()
        return True


# ==================== 主应用 ====================
class PowerSafetyApp(App):
    def build(self):
        Window.clearcolor = (0.95, 0.97, 0.99, 1)
        self.questions = []
        self.filtered_questions = []
        self.search_text = ""
        self.is_loading = False
        self.current_tab = 'all'
        self.fav_manager = FavoriteManager()

        # 主布局
        main_layout = BoxLayout(orientation='vertical', spacing=8, padding=12)

        # 标题
        title_label = Label(
            text='[b]⚡ 电力安全题库[/b]',
            markup=True,
            font_name='SimSun',
            font_size='24sp',
            size_hint_y=None,
            height=45,
            color=(0.1, 0.2, 0.4, 1)
        )
        main_layout.add_widget(title_label)

        # 搜索框
        search_box = BoxLayout(size_hint_y=None, height=48, spacing=8)
        self.search_input = TextInput(
            hint_text='输入关键词搜索...',
            font_name='SimSun',
            multiline=False,
            background_color=(1, 1, 1, 1),
            font_size='15sp',
            padding=[12, 8, 12, 8]
        )
        self.search_input.bind(text=self.on_search)
        
        search_btn = Button(
            text='搜索',
            font_name='SimSun',
            size_hint_x=None,
            width=70,
            background_color=(0.2, 0.5, 0.8, 1)
        )
        search_btn.bind(on_press=self.do_search)
        
        clear_btn = Button(
            text='✕',
            font_name='SimSun',
            size_hint_x=None,
            width=45,
            background_color=(0.8, 0.3, 0.3, 1)
        )
        clear_btn.bind(on_press=self.clear_search)
        
        search_box.add_widget(self.search_input)
        search_box.add_widget(search_btn)
        search_box.add_widget(clear_btn)
        main_layout.add_widget(search_box)

        # 工具栏
        tool_box = BoxLayout(size_hint_y=None, height=48, spacing=8)
        
        refresh_btn = Button(
            text='🔄 更新题库',
            font_name='SimSun',
            background_color=(0.2, 0.5, 0.7, 1)
        )
        refresh_btn.bind(on_press=self.download_questions)
        
        ocr_btn = Button(
            text='📷 OCR识别',
            font_name='SimSun',
            background_color=(0.6, 0.4, 0.8, 1)
        )
        ocr_btn.bind(on_press=self.show_ocr_dialog)
        
        tool_box.add_widget(refresh_btn)
        tool_box.add_widget(ocr_btn)
        main_layout.add_widget(tool_box)

        # Tab切换（全部题目/收藏）
        tab_box = BoxLayout(size_hint_y=None, height=40, spacing=8)
        
        self.all_tab_btn = Button(
            text='📚 全部题目',
            font_name='SimSun',
            background_color=(0.2, 0.5, 0.8, 1)
        )
        self.all_tab_btn.bind(on_press=lambda x: self.switch_tab('all'))
        
        self.fav_tab_btn = Button(
            text='⭐ 收藏夹 (0)',
            font_name='SimSun',
            background_color=(0.6, 0.6, 0.6, 0.5)
        )
        self.fav_tab_btn.bind(on_press=lambda x: self.switch_tab('favorites'))
        
        tab_box.add_widget(self.all_tab_btn)
        tab_box.add_widget(self.fav_tab_btn)
        main_layout.add_widget(tab_box)

        # 信息标签
        self.info_label = Label(
            text='📊 正在加载题库...',
            font_name='SimSun',
            size_hint_y=None,
            height=30,
            font_size='14sp',
            color=(0.3, 0.3, 0.3, 1)
        )
        main_layout.add_widget(self.info_label)

        # 进度条
        self.progress_bar = ProgressBar(
            size_hint_y=None,
            height=6,
            value=0
        )
        self.progress_bar.opacity = 0
        main_layout.add_widget(self.progress_bar)

        # 题目列表
        self.question_list = ScrollView()
        self.list_content = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            spacing=6
        )
        self.list_content.bind(minimum_height=self.list_content.setter('height'))
        self.question_list.add_widget(self.list_content)
        main_layout.add_widget(self.question_list)

        # 状态栏
        self.status_label = Label(
            text='💡 正在连接服务器...',
            font_name='SimSun',
            size_hint_y=None,
            height=30,
            font_size='13sp',
            color=(0.4, 0.4, 0.4, 1)
        )
        main_layout.add_widget(self.status_label)

        # 启动后自动加载
        Clock.schedule_once(self.auto_load, 0.5)
        
        return main_layout

    # ==================== Tab切换 ====================
    def switch_tab(self, tab):
        """切换标签页"""
        self.current_tab = tab
        
        if tab == 'all':
            self.all_tab_btn.background_color = (0.2, 0.5, 0.8, 1)
            self.fav_tab_btn.background_color = (0.6, 0.6, 0.6, 0.5)
            self.search_input.disabled = False
            self.refresh_list()
            self.info_label.text = f'📊 共 {len(self.filtered_questions)} 道题目'
        else:  # favorites
            self.all_tab_btn.background_color = (0.6, 0.6, 0.6, 0.5)
            self.fav_tab_btn.background_color = (0.2, 0.5, 0.8, 1)
            self.search_input.disabled = True
            self.search_input.text = ''
            self.refresh_favorites()
    
    def refresh_favorites(self):
        """刷新收藏列表"""
        fav_ids = self.fav_manager.get_all()
        fav_questions = [q for q in self.questions if str(q.id) in fav_ids]
        self.fav_tab_btn.text = f'⭐ 收藏夹 ({len(fav_ids)})'
        
        self.list_content.clear_widgets()
        
        if not fav_questions:
            self.list_content.add_widget(Label(
                text='💡 还没有收藏的题目\n点击题目卡片上的 ☆ 按钮收藏',
                font_name='SimSun',
                font_size='16sp',
                color=(0.5, 0.5, 0.5, 1),
                halign='center',
                valign='middle'
            ))
            self.info_label.text = '⭐ 收藏夹为空'
            return
        
        for q in fav_questions:
            card = QuestionCard(q, self)
            self.list_content.add_widget(card)
        
        self.info_label.text = f'⭐ 收藏夹 ({len(fav_questions)} 题)'

    def update_favorite_count(self):
        """更新收藏计数"""
        count = len(self.fav_manager.get_all())
        self.fav_tab_btn.text = f'⭐ 收藏夹 ({count})'
        if self.current_tab == 'favorites':
            self.refresh_favorites()

    # ==================== 自动加载 ====================
    def auto_load(self, dt):
        if os.path.exists(CACHE_FILE):
            self.status_label.text = '📂 加载本地缓存...'
            if self.load_from_file(CACHE_FILE):
                self.status_label.text = '✅ 已加载本地题库'
                Clock.schedule_once(self.check_update, 1)
                return
        
        self.status_label.text = '🌐 从服务器下载题库...'
        self.download_questions()

    def check_update(self, dt):
        pass

    # ==================== 下载题库 ====================
    def download_questions(self, *args):
        if self.is_loading:
            return
        
        self.is_loading = True
        self.progress_bar.opacity = 1
        self.progress_bar.value = 0
        self.status_label.text = '🌐 正在下载题库...'
        
        def on_progress(req, current, total):
            if total > 0:
                self.progress_bar.value = current / total * 100
        
        def on_success(req, result):
            self.is_loading = False
            self.progress_bar.opacity = 0
            try:
                if isinstance(result, bytes):
                    xml_str = result.decode('utf-8')
                else:
                    xml_str = result
                
                with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                    f.write(xml_str)
                
                root = ET.fromstring(xml_str)
                self.parse_xml(root)
                self.status_label.text = f'✅ 下载成功！共 {len(self.questions)} 题'
                self.info_label.text = f'📊 共 {len(self.questions)} 道题目 (已更新)'
                
            except Exception as e:
                self.status_label.text = f'❌ 解析失败: {str(e)}'
                if os.path.exists(CACHE_FILE):
                    self.load_from_file(CACHE_FILE)
        
        def on_failure(req, error):
            self.is_loading = False
            self.progress_bar.opacity = 0
            self.status_label.text = f'❌ 下载失败: {error}'
            if os.path.exists(CACHE_FILE):
                self.status_label.text = '📂 使用本地缓存...'
                self.load_from_file(CACHE_FILE)
            else:
                self.status_label.text = '⚠️ 无本地缓存，请检查网络'
                self.info_label.text = '⚠️ 请检查网络连接'

        try:
            req = UrlRequest(
                SERVER_URL,
                on_success=on_success,
                on_failure=on_failure,
                on_progress=on_progress
            )
        except Exception as e:
            self.is_loading = False
            self.progress_bar.opacity = 0
            self.status_label.text = f'❌ 连接失败: {str(e)}'
            if os.path.exists(CACHE_FILE):
                self.load_from_file(CACHE_FILE)

    # ==================== 加载本地文件 ====================
    def load_from_file(self, file_path):
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            self.parse_xml(root)
            self.info_label.text = f'📊 共 {len(self.questions)} 道题目 (本地)'
            self.status_label.text = f'✅ 加载成功: {os.path.basename(file_path)}'
            return True
        except Exception as e:
            self.status_label.text = f'❌ 加载失败: {str(e)}'
            return False

    # ==================== 解析XML ====================
    def parse_xml(self, root):
        self.questions = []
        
        for elem in root.findall('question'):
            qid = elem.get('id', str(len(self.questions) + 1))
            question_text = elem.findtext('question') or ''
            
            options = []
            options_elem = elem.find('options')
            if options_elem is not None:
                for opt in options_elem.findall('option'):
                    options.append(opt.text or '')
            
            answer = elem.findtext('answer') or ''
            explanation = elem.findtext('explanation') or ''
            
            if question_text and options:
                self.questions.append(Question(
                    qid, question_text, options, answer, explanation
                ))
        
        self.filtered_questions = self.questions[:]
        self.update_favorite_count()
        if self.current_tab == 'all':
            self.refresh_list()
            self.info_label.text = f'📊 共 {len(self.questions)} 道题目'
        else:
            self.refresh_favorites()

    # ==================== 搜索功能 ====================
    def on_search(self, instance, value):
        self.search_text = value.strip()
        if self.current_tab == 'all':
            self.do_search()

    def do_search(self, *args):
        if self.current_tab == 'favorites':
            return
        
        if not self.questions:
            self.status_label.text = '⚠️ 请先加载题库'
            return

        if not self.search_text:
            self.filtered_questions = self.questions[:]
        else:
            keyword = self.search_text.lower()
            self.filtered_questions = [
                q for q in self.questions
                if keyword in q.question.lower() or keyword in q.answer.lower()
            ]
        
        self.refresh_list()
        self.info_label.text = f'📊 找到 {len(self.filtered_questions)} 题'

    def clear_search(self, *args):
        self.search_input.text = ''
        self.search_text = ''
        if self.current_tab == 'all':
            self.filtered_questions = self.questions[:]
            self.refresh_list()
            self.info_label.text = f'📊 共 {len(self.questions)} 道题目'
            self.status_label.text = '已清除搜索'

    def refresh_list(self):
        self.list_content.clear_widgets()
        
        if not self.filtered_questions:
            self.list_content.add_widget(Label(
                text='暂无匹配的题目',
                font_name='SimSun',
                font_size='16sp',
                color=(0.5, 0.5, 0.5, 1)
            ))
            return
        
        for q in self.filtered_questions:
            card = QuestionCard(q, self)
            self.list_content.add_widget(card)

    # ==================== OCR识别 ====================
    def show_ocr_dialog(self, *args):
        if not OCR_AVAILABLE:
            self.status_label.text = '⚠️ OCR未安装'
            return

        content = BoxLayout(orientation='vertical', spacing=12, padding=16)
        
        content.add_widget(Label(
            text='📷 选择识别方式',
            font_name='SimSun',
            font_size='18sp',
            size_hint_y=None,
            height=40,
            color=(0.1, 0.2, 0.4, 1)
        ))
        
        btn_box = BoxLayout(size_hint_y=None, height=60, spacing=12)
        
        camera_btn = Button(
            text='📸 拍照识别',
            font_name='SimSun',
            background_color=(0.2, 0.5, 0.8, 1)
        )
        camera_btn.bind(on_press=self.camera_ocr)
        
        file_btn = Button(
            text='🖼️ 选择图片',
            font_name='SimSun',
            background_color=(0.3, 0.6, 0.3, 1)
        )
        file_btn.bind(on_press=self.file_ocr)
        
        btn_box.add_widget(camera_btn)
        btn_box.add_widget(file_btn)
        content.add_widget(btn_box)
        
        self.ocr_result_label = Label(
            text='识别结果将显示在这里',
            font_name='SimSun',
            size_hint_y=None,
            height=60,
            font_size='13sp',
            color=(0.2, 0.2, 0.2, 1)
        )
        content.add_widget(self.ocr_result_label)
        
        close_btn = Button(
            text='关闭',
            font_name='SimSun',
            size_hint_y=None,
            height=44,
            background_color=(0.6, 0.3, 0.3, 1)
        )
        content.add_widget(close_btn)
        
        self.ocr_popup = Popup(
            title='OCR 题目识别',
            content=content,
            size_hint=(0.9, 0.7),
            auto_dismiss=True
        )
        close_btn.bind(on_press=self.ocr_popup.dismiss)
        self.ocr_popup.open()

    def camera_ocr(self, *args):
        if not CAMERA_AVAILABLE:
            self.status_label.text = '⚠️ 摄像头不可用'
            return
        
        camera_content = BoxLayout(orientation='vertical')
        
        camera_view = XCamera()
        camera_content.add_widget(camera_view)
        
        btn_box = BoxLayout(size_hint_y=None, height=60, spacing=12, padding=10)
        
        capture_btn = Button(
            text='📸 拍照',
            font_name='SimSun',
            background_color=(0.2, 0.5, 0.8, 1)
        )
        cancel_btn = Button(
            text='取消',
            font_name='SimSun',
            background_color=(0.6, 0.3, 0.3, 1)
        )
        
        btn_box.add_widget(capture_btn)
        btn_box.add_widget(cancel_btn)
        camera_content.add_widget(btn_box)
        
        camera_popup = Popup(
            title='拍照识别',
            content=camera_content,
            size_hint=(0.95, 0.95),
            auto_dismiss=False
        )
        
        def on_capture(inst):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_path = f'ocr_capture_{timestamp}.png'
            camera_view.export_to_png(file_path)
            camera_popup.dismiss()
            
            self.status_label.text = '📷 正在识别...'
            self.do_ocr_from_path(file_path)
        
        def on_cancel(inst):
            camera_popup.dismiss()
        
        capture_btn.bind(on_press=on_capture)
        cancel_btn.bind(on_press=on_cancel)
        camera_popup.open()

    def file_ocr(self, *args):
        content = FileChooserListView(
            filters=['*.png', '*.jpg', '*.jpeg', '*.bmp']
        )
        
        popup = Popup(
            title='选择图片',
            content=content,
            size_hint=(0.9, 0.8),
            auto_dismiss=True
        )
        
        def on_select(chooser, selection, *args):
            if selection:
                popup.dismiss()
                self.status_label.text = '📷 正在识别...'
                self.do_ocr_from_path(selection[0])
        
        content.bind(on_submit=on_select)
        popup.open()

    def do_ocr_from_path(self, path):
        try:
            img = Image.open(path)
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.0)
            
            custom_config = r'--oem 3 --psm 6 -l chi_sim+eng'
            text = pytesseract.image_to_string(img, config=custom_config)
            text = text.strip()
            
            if not text:
                self.status_label.text = '⚠️ 未识别到文字'
                return
            
            lines = text.split('\n')
            search_text = ' '.join([ln.strip() for ln in lines[:5] if ln.strip()])
            
            if search_text:
                if hasattr(self, 'ocr_result_label'):
                    self.ocr_result_label.text = f'识别结果:\n{search_text[:80]}...'
                
                self.search_input.text = search_text[:50]
                self.status_label.text = '✅ OCR识别完成'
                if self.current_tab == 'all':
                    self.do_search()
                else:
                    self.switch_tab('all')
                    self.do_search()
                
        except Exception as e:
            self.status_label.text = f'❌ OCR失败: {str(e)}'


def main():
    PowerSafetyApp().run()


if __name__ == '__main__':
    main()