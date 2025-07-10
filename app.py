import streamlit as st
import requests
import datetime
import os
import google.generativeai as genai
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json

# --- Streamlitのシークレット機能から情報を読み込む ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    GOOGLE_CREDS_INFO = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    # ★ 質問1の答え：フォルダIDもSecretsから読み込む
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"] 
except Exception as e:
    st.error(f"必要な認証情報が正しく設定されていません。StreamlitのSecretsを確認してください。エラー: {e}")
    st.stop()

# (ここから下の to_wareki_jp, translate_jp..., analyze_and_explain_paper, search_pubmed, create_google_doc 関数群は、一切の変更なし)
# (省略...)
# --- Streamlitアプリのメインロジック ---

# ★ 質問3の答え：ページ全体のデザインを設定
st.set_page_config(
    page_title="AI論文サマリー",
    page_icon="🔬",  # タブに表示されるアイコンを、より知的なものに
    layout="wide"  # コンテンツの表示幅を広げて、よりリッチに見せる
)

# --- ヘッダー部分 ---
st.title("🔬 AIアシスタントによる最新医学論文サマリー")
st.markdown("---") # 区切り線を入れる
st.subheader("世界中の最新論文から、知りたい情報を、3分で。")
st.write("キーワードを日本語で入力するだけで、AIが海外の最新論文を自動で検索・分析し、要点をまとめたサマリーレポートを、あなたのGoogleドライブに作成します。")

st.write("") # 空白行を入れて、余白を作る

# --- メインの入力フォーム ---
with st.form("search_form"):
    st.markdown("##### 検索したいキーワードを入力してください")
    
    # ★ 質問3の答え：入力欄を2つに分けて、より分かりやすく
    col1, col2 = st.columns([3, 1]) # 3:1の幅で列を分割
    with col1:
        jp_disease_input = st.text_input(
            "キーワード（複数可）", 
            placeholder="例: 糖尿病, 高血圧",
            label_visibility="collapsed" # ラベルを非表示にしてスッキリ見せる
        )
    with col2:
        submitted = st.form_submit_button("レポート作成を開始", use_container_width=True)


if submitted and jp_disease_input:
    # (ここから下の処理ループは、フォルダIDの引数が不要になる以外、変更なし)
    # (省略...)

    st.success("すべての処理が完了しました！")
