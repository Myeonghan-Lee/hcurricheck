import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import io
import time
import os
from fpdf import FPDF

# --- 1. 세션 상태 초기화 ---
if 'analysis_data' not in st.session_state:
    st.session_state.analysis_data = []
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

def reset_all():
    st.session_state.analysis_data = []
    st.session_state.uploader_key += 1
    st.rerun()

# --- 2. 점검 지침 (요청하신 사항 반영) ---
CALCULATION_LOGIC = """
[학점 계산 및 검증 핵심 지침]
1. [x] 제외 규칙: 학점 칸에 대괄호가 있는 숫자(예: [2], [4])는 반별 교차 편성 등을 의미하므로 합계 계산 시 0으로 처리하고 절대 합산하지 마시오.
2. 학기별 총합: (학교 지정 과목 학점) + (선택 과목 배정 학점) + (창의적 체험활동 학점)을 합산. 
   - 선택 과목의 '12(택3)' 형식에서 괄호 앞의 숫자 12를 해당 학기 배정 학점으로 사용.
3. 필수 이수학점 정밀 체크 (지정+선택 합산):
   - 국어(10), 수학(10), 영어(10), 사회(10), 과학(12), 체육(10), 예술(10) 학점 확인.
   - 기술·가정/정보/제2외국어/한문/교양 교과군: 이들 교과목의 이수 학점 총합이 16학점 이상인지 확인.
   - 학교 지정 학점만으로 부족할 경우, 해당 교과군 내의 '학생 선택' 학점을 찾아 반드시 합산하여 판정할 것.
4. 결과 출력: 상세근거에 계산식 명시 (예: 지정(22)+선택(7)+창체(3)=32 / [2] 제외됨)
"""

# --- 3. PDF 생성 클래스 (한글 폰트 대응) ---
class PDF(FPDF):
    def __init__(self):
        super().__init__()
        # 폰트 파일 존재 여부 확인 후 등록
        if os.path.exists("NanumGothic.ttf"):
            self.add_font("Nanum", "", "NanumGothic.ttf")
            self.font_name = "Nanum"
        else:
            self.font_name = "Arial" # 폰트 없을 경우 기본 폰트 (한글 깨짐 주의)

    def header(self):
        self.set_font(self.font_name, size=12)
        self.cell(0, 10, 'Education Curriculum Inspection Report', ln=True, align='C')
        self.ln(5)

def create_pdf(data_list):
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    for data in data_list:
        pdf.add_page()
        pdf.set_font(pdf.font_name, size=16)
        pdf.cell(0, 10, f"School: {data.get('학교명', 'N/A')}", ln=True)
        pdf.ln(5)
        
        pdf.set_font(pdf.font_name, size=10)
        for item in data.get('점검리포트', []):
            # 텍스트가 너무 길 경우 multi_cell 사용
            txt = f"[{item['항목']}] 판정: {item['판정']}\n근거: {item['상세근거']}"
            pdf.multi_cell(0, 8, txt, border=1)
            pdf.ln(2)
        
        pdf.ln(5)
        pdf.set_font(pdf.font_name, size=11)
        pdf.multi_cell(0, 7, f"General Opinion:\n{data.get('종합의견', '')}")
        
    return pdf.output()

# --- 4. 모델 및 분석 함수 ---
def get_model(api_key, school_type):
    genai.configure(api_key=api_key)
    rules = CALCULATION_LOGIC + "\n[일반 지침] 1.총이수(192), 2.필수(84), 3.학기완결성, 4.위계성 등 점검."
    if school_type == "과학중점학교":
        rules += "\n[과학중점] 1학년과학10학점, 과학8과목, 수학/정보 심화 필수."
    
    instruction = f"고등학교 교육과정 전문가로서 아래 지침을 엄수하여 JSON으로 응답하세요.\n{rules}"
    return genai.GenerativeModel('gemini-1.5-flash', system_instruction=instruction)

def analyze_excel(model, file):
    try:
        all_sheets = pd.read_excel(file, sheet_name=None)
        content = ""
        for name, df in all_sheets.items():
            content += f"\n[Sheet: {name}]\n{df.fillna('').to_csv(index=False)}"
        
        response = model.generate_content(f"파일명: {file.name}\n{content}")
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_text)
    except Exception as e:
        return {"학교명": file.name, "점검리포트": [{"항목": "에러", "판정": "X", "상세근거": str(e)}], "종합의견": "분석 중 오류가 발생했습니다."}

# --- 5. UI 구성 ---
st.set_page_config(page_title="고등학교 교육과정 점검 시스템", layout="wide")
st.title("🏫 교육과정 정밀 점검 & PDF 리포트")

with st.sidebar:
    st.header("⚙️ Settings")
    api_key = st.text_input("Gemini API Key", type="password")
    school_type = st.selectbox("School Type", ["일반 고등학교", "과학중점학교"])
    if st.button("🔄 Reset All"): reset_all()

u_key = f"u_{st.session_state.get('uploader_key', 0)}"
uploaded_files = st.file_uploader("엑셀 파일(.xlsx) 업로드", type=['xlsx'], accept_multiple_files=True, key=u_key)

if api_key and uploaded_files:
    if st.button("🔍 점검 시작", type="primary", use_container_width=True):
        model = get_model(api_key, school_type)
        st.session_state.analysis_data = []
        
        for file in uploaded_files:
            with st.spinner(f"{file.name} 분석 중..."):
                result = analyze_excel(model, file)
                st.session_state.analysis_data.append(result)
        st.success("분석이 완료되었습니다!")

# --- 결과 및 다운로드 ---
if st.session_state.analysis_data:
    st.divider()
    for idx, data in enumerate(st.session_state.analysis_data):
        with st.expander(f"📄 {data.get('학교명', '알 수 없는 학교')} 결과"):
            st.table(pd.DataFrame(data['점검리포트']))
            st.info(data['종합의견'])
            
            # 개별 PDF
            indiv_pdf = create_pdf([data])
            st.download_button("📥 PDF 다운로드", data=indiv_pdf, file_name=f"{data['학교명']}_점검표.pdf", mime="application/pdf", key=f"btn_{idx}")

    st.divider()
    # 통합 PDF
    if len(st.session_state.analysis_data) > 1:
        total_pdf = create_pdf(st.session_state.analysis_data)
        st.download_button("📥 모든 학교 통합 리포트(PDF) 다운로드", data=total_pdf, file_name="전체_점검보고서.pdf", mime="application/pdf", use_container_width=True, type="primary")
