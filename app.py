import streamlit as st
import requests
import datetime
import os
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json

# --- Streamlitのシークレット機能から情報を読み込む ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("Gemini APIキーが設定されていません。StreamlitのSecretsを確認してください。")
    st.stop()

# --- Google認証情報の準備 (Workload Identity連携) ---
def get_google_credentials():
    # Streamlit Cloud上でGitHub Actions経由で実行される場合、
    # google-github-actions/auth@v2 が設定する環境変数から自動で認証情報が読み込まれる。
    # この関数は、その認証情報にGoogle Drive APIの操作範囲(scope)を付与する役割を持つ。
    try:
        # このライブラリは、標準的な環境変数を探して自動で認証を試みる
        creds, project_id = google.auth.default(scopes=['https://www.googleapis.com/auth/drive'])
        return creds
    except Exception as e:
        st.error(f"Google Cloudの認証に失敗しました。管理者にお問い合わせください。エラー: {e}")
        return None

# --- ここから下の関数群は、一切の変更なし ---
def to_wareki_jp(y, m):
    try: y, m = int(y), int(m)
    except (ValueError, TypeError): return f"{y}年{m}月"
    if y >= 2019: era, era_year = "令和", y - 2018
    elif y >= 1989: era, era_year = "平成", y - 1988
    elif y >= 1926: era, era_year = "昭和", y - 1925
    else: return f"{y}年{m}月"
    year_str = "元年" if era_year == 1 else str(era_year)
    return f"{era}{year_str}年{m}月"

def translate_jp_to_en_for_search(jp_term, model):
    if not model: return ""
    prompt = f"以下の日本の病名を、PubMedで論文を検索するために最も適した英語の医学用語に変換してください。\n余計な解説や文章は一切含めず、英語の医学用語のみを返答してください。\n\n[日本の病名]\n{jp_term}\n\n[英語の医学用語]"
    try: response = model.generate_content(prompt); return response.text.strip()
    except Exception as e: st.warning(f"'{jp_term}'の英語への変換中にエラー: {e}"); return ""

def analyze_and_explain_paper(paper_info, model):
    if not model: return "（分析・解説できませんでした）"
    prompt = f"""
あなたは、最新の医学論文の要点を、日本の多忙な医師向けに分かりやすく解説する、非常に優秀なサイエンス・コミュニケーターです。
以下の論文情報（タイトル、著者、発表日、要旨）を元に、下記の【出力フォーマット】に厳密に従って、日本語で解説文を生成してください。
絶対に、元の英語のタイトルや要旨は出力に含めないでください。
---
[論文情報]
- タイトル: {paper_info['title']}
- 著者: {paper_info['authors']}
- 発表日: {paper_info['pub_date_jp']}
- 要旨: {paper_info['abstract']}
---
【出力フォーマット】
■ タイトル: （ここに日本語に翻訳したタイトル）
■ 発表日: {paper_info['pub_date_jp']}
■ 論文の結論: （この論文が最終的に何を言っているのか、最も重要な結論を1〜2行で要約してください）
■ 実験の概要: （「誰/何を対象に」「何をして」「何を調べたのか」を具体的に記述してください。例：「〇〇マウスを用いて、△△ワクチンを接種し、××に対する抗体価の変化を測定した」）
■ 結果と考察: （実験の結果、何が明らかになったのかを記述してください。その結果が臨床的にどのような意味を持つか、今後の展望なども含めて解説してください）
"""
    try: response = model.generate_content(prompt); return response.text.strip()
    except Exception as e: st.warning(f"Gemini APIでの論文解説中にエラー: {e}"); return "（論文の解説中にエラーが発生しました）"

def search_pubmed(english_term, days=30):
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"    
    end_date = datetime.date.today(); start_date = end_date - datetime.timedelta(days=days)
    date_query = f"{start_date.strftime('%Y/%m/%d')}[PDAT] : {end_date.strftime('%Y/%m/%d')}[PDAT]"
    search_url = f"{base_url}esearch.fcgi"; search_params = {"db": "pubmed", "term": f"({english_term}[MeSH Terms] OR {english_term}[Title/Abstract]) AND ({date_query})", "retmode": "json", "retmax": 5}
    try:
        response = requests.get(search_url, params=search_params); response.raise_for_status(); data = response.json()
        id_list = data.get("esearchresult", {}).get("idlist", [])        
        if not id_list: return []
        fetch_url = f"{base_url}efetch.fcgi"; fetch_params = {"db": "pubmed", "id": ",".join(id_list), "retmode": "xml"}        
        response = requests.get(fetch_url, params=fetch_params); response.raise_for_status()
        from xml.etree import ElementTree as ET
        root = ET.fromstring(response.content); articles = []
        month_map = {'Jan': '1', 'Feb': '2', 'Mar': '3', 'Apr': '4', 'May': '5', 'Jun': '6', 'Jul': '7', 'Aug': '8', 'Sep': '9', 'Oct': '10', 'Nov': '11', 'Dec': '12'}
        for article in root.findall(".//PubmedArticle"):
            abstract_text = article.findtext(".//AbstractText")
            if not abstract_text: continue
            pub_date_node = article.find(".//PubDate")
            if pub_date_node is not None:
                year = pub_date_node.findtext("Year", "不明"); month_str = pub_date_node.findtext("Month", "不明"); month = month_map.get(month_str, month_str) 
                pub_date_jp_str = to_wareki_jp(year, month)
            else: pub_date_jp_str = "発表日不明"
            articles.append({"title": article.findtext(".//ArticleTitle") or "N/A", "authors": ", ".join([f"{a.findtext('LastName')} {a.findtext('Initials')}" for a in article.findall('.//Author') if a.findtext('LastName')]) or "N/A", "abstract": abstract_text, "url": f"https://pubmed.ncbi.nlm.nih.gov/{article.findtext('.//PMID')}/", "pub_date_jp": pub_date_jp_str})
        return articles
    except requests.RequestException as e: st.warning(f"PubMed APIでエラー: {e}"); return []

def create_google_doc(title, content, creds, folder_id):
    try:
        # Google Docs APIとDrive APIの両方を使う
        drive_service = build('drive', 'v3', credentials=creds)
        docs_service = build('docs', 'v1', credentials=creds)
        
        # まずDriveに空のドキュメントを作成
        file_metadata = {'name': title, 'mimeType': 'application/vnd.google-apps.document', 'parents': [folder_id]}
        document = drive_service.files().create(body=file_metadata).execute()
        doc_id = document.get('id')
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        
        # 次にDocs APIで内容を書き込む
        requests_body = [{'insertText': {'location': {'index': 1}, 'text': content}}]
        docs_service.documents().batchUpdate(documentId=doc_id, body={'requests': requests_body}).execute()
        return doc_url
    except HttpError as err: st.error(f"Google Drive/Docs APIでエラー: {err}"); return None

# --- Streamlitアプリのメインロジック ---
st.set_page_config(page_title="最新医学論文おまかせサマリー", layout="centered")
st.title("👨‍⚕️ 最新医学論文おまかせサマリー")
st.markdown("知りたい病名やキーワードを日本語で入力すると、AIが海外の最新論文を検索・分析し、要点解説レポートを自動でGoogleドキュメントに作成します。")

# ★レポートを保存するGoogle DriveフォルダのIDを入力させる
DRIVE_FOLDER_ID = st.text_input("レポートを保存するGoogle DriveフォルダのIDを入力してください", help="Googleドライブで、このアプリ専用に作成・共有設定したフォルダを開き、URLの最後の部分にある英数字の羅列を貼り付けてください。")

with st.form("search_form"):
    jp_disease_input = st.text_input("ここに病名やキーワードを入力してください（例: 糖尿病, 高血圧）", "")
    submitted = st.form_submit_button("レポート作成を開始")

if submitted and jp_disease_input and DRIVE_FOLDER_ID:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    creds = get_google_credentials()
    if not creds:
        st.stop()

    jp_disease_list = [name.strip() for name in jp_disease_input.split(',') if name.strip()]
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    st.info("処理を開始しました。完了まで数分かかることがあります…")

    for jp_disease in jp_disease_list:
        with st.status(f"【{jp_disease}】のレポートを作成中…", expanded=True) as status:
            st.write("1. 英語キーワードに変換中...")
            english_term = translate_jp_to_en_for_search(jp_disease, model)
            if not english_term: st.warning(f"変換失敗。スキップします。"); status.update(label="キーワード変換に失敗しました", state="error"); continue
            st.write(f"-> `{english_term}`")
            
            st.write("2. PubMedで論文を検索中...")
            papers = search_pubmed(english_term)
            if not papers: st.warning(f"論文が見つかりませんでした。"); status.update(label="論文が見つかりませんでした", state="warning"); continue
            st.write(f"-> {len(papers)}件の論文を発見")

            st.write("3. AIが分析・解説を作成中…")
            final_content = f"【{jp_disease}】に関する最新論文解説レポート\n作成日: {today_str}\n\n========================================\n\n"
            for j, paper in enumerate(papers):
                st.write(f"   - 論文 {j+1}/{len(papers)} を処理中...")
                explanation = analyze_and_explain_paper(paper, model)
                final_content += f"【論文 {j+1}】\n{explanation}\n\n■ 参照元URL: {paper['url']}\n\n----------------------------------------\n\n"
            
            st.write("4. Googleドキュメントを作成中...")
            doc_title = f"{jp_disease} 最新論文解説レポート ({today_str})"
            doc_url = create_google_doc(doc_title, final_content, creds, DRIVE_FOLDER_ID)
            if doc_url:
                st.success(f"「{jp_disease}」のレポートが完成しました！")
                st.markdown(f"**[完成したレポートを開く]({doc_url})**", unsafe_allow_html=True)
                status.update(label="レポート作成完了！", state="complete")
            else:
                status.update(label="ドキュメント作成に失敗", state="error")

    st.success("すべての処理が完了しました！")
