import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import io
import time
from fpdf import FPDF

# --- 1. 앱 설정 및 세션 상태 초기화 ---
st.set_page_config(page_title="고등학교 교육과정 정밀 점검 시스템", layout="wide")

if 'analysis_data' not in st.session_state:
    st.session_state.analysis_data = []
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

def reset_all():
    st.session_state.analysis_data = []
    st.session_state.uploader_key += 1
    st.rerun()

# --- 2. 점검 지침 정의 (요구사항 반영) ---

CALCULATION_LOGIC = """
[학점 계산 및 검증 핵심 지침]
1. [x] 제외 규칙: 학점 칸에 대괄호가 있는 숫자(예: [2], [4])는 반별 교차 편성 등을 의미하므로 합계 계산 시 0으로 처리하고 절대 합산하지 마시오.
2. 학기별 총합: (학교 지정 과목 학점) + (선택 과목 배정 학점 X) + (창의적 체험활동 학점)을 합산. 
   - 선택 과목의 '12(택3)' 형식에서 괄호 앞의 숫자 12를 사용.
3. 필수 이수학점 정밀 체크:
   - 국어(10), 수학(10), 영어(10), 사회(10), 과학(12), 체육(10), 예술(10) 학점 확인.
   - 기술·가정/정보/제2외국어/한문/교양 교과군: 이들 과목의 합계가 최소 16학점 이상이어야 함.
   - 중요: '학교 지정' 학점만으로 부족할 경우, 해당 교과군 내의 '학생 선택' 과목(필수 선택 그룹 등)을 찾아 합산하여 충족 여부를 판단할 것.
4. 결과 출력: 상세근거에 "1-1학기: 지정(22)+선택(7)+창체(3)=32 / [2] 제외됨" 과 같이 명시.
"""

GENERAL_RULES = f"""
{CALCULATION_LOGIC}
[일반 지침]
1.총이수학점(192이상), 2.필수이수학점(84이상), 3.학기단위완결성, 4.공통과목우선편성, 
5.과목위계성(로마자 과목), 6.학기간학점균형(격차5), 7.초과이수적정성, 
8.과목별학점범위, 9.교과군별필수충족(지정+선택 합산), 10.2022개정과목사용, 
11.국수영총합(81이내), 12.한국사(각3학점), 13.체육(매학기 편성), 14.종교선택권
"""

SCIENCE_CORE_RULES = "[과학중점학교 지침] 1학년 과학 10학점, 과학 8과목 이상, 수학/정보 심화 편성 필수."

# --- 3. PDF 생성 함수 ---

class PDF(FPDF):
    def header(self):
        # 한국어 폰트 설정 (폰트 파일이 실행 경로에 있어야 함. 여기서는 기본 폰트 사용 예시)
        # 실제 환경에서는 NanumGothic.ttf 등을 추가해야 깨지지 않습니다.
        try:
            self.add_font('Nanum', '', 'NanumGothic.ttf') # 폰트 파일 필요
            self.set_font('Nanum', '', 12)
        except:
            self.set_font('Helvetica', 'B', 12)
        self.cell(0, 10, 'Curriculum Inspection Report', ln=True, align='C')
        self.ln(5)

def create_pdf(data_list, filename="report.pdf"):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # 한국어 폰트 처리 (폰트 경로 주의)
    # 폰트가 없는 환경을 위해 에러 처리를 하되, 실제 사용 시에는 반드시 ttf 파일을 넣으세요.
    try:
        # 이 코드 실행 경로에 NanumGothic.ttf가 있다고 가정하거나 아래 경로 수정
        pdf.add_font("Nanum", "", "NanumGothic.ttf")
        font_name = "Nanum"
    except:
        font_name = "Arial" # 한국어는 깨질 수 있음

    for data in data_list:
        pdf.add_page()
        pdf.set_font(font_name, size=16)
        pdf.cell(0, 10, f"점검 리포트: {data.get('학교명', 'Unknown')}", ln=True, align='C')
        pdf.ln(10)
        
        pdf.set_font(font_name, size=10)
        # 점검표 테이블
        for item in data.get('점검리포트', []):
            pdf.multi_cell(0, 8, f"[{item['항목']}] 판정: {item['판정']}\n근거: {item['상세근거']}\n", border=1)
            pdf.ln(2)
        
        pdf.ln(5)
        pdf.set_font(font_name, size=12)
        pdf.multi_cell(0, 10, f"종합 의견:\n{data.get('종합의견', '')}", border=0)
        
    return pdf.output()

# --- 4. 메인 로직 ---

def get_model(api_key, school_type):
    genai.configure(api_key=api_key)
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    target = next((m for m in ["models/gemini-1.5-flash", "gemini-1.5-flash"] if m in available_models), available_models[0])
    
    rules = GENERAL_RULES + (SCIENCE_CORE_RULES if school_type == "과학중점학교" else "")
    instruction = f"고등학교 교육과정 전문가로서 JSON으로 응답하세요.\n{rules}\nJSON: {{\"학교명\": \"\", \"점검리포트\": [{{ \"항목\": \"\", \"판정\": \"\", \"상세근거\": \"\" }}], \"종합의견\": \"\"}}"
    return genai.GenerativeModel(model_name=target, system_instruction=instruction)

def analyze_excel(model, file):
    all_sheets = pd.read_excel(file, sheet_name=None)
    content = ""
    for name, df in all_sheets.items():
        content += f"\n[시트: {name}]\n{df.fillna('').to_csv(index=False)}"
    
    response = model.generate_content(f"파일명: {file.name}\n데이터:\n{content}")
    return json.loads(response.text.replace('```json', '').replace('```', '').strip())

# --- 5. UI ---

with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Gemini API Key", type="password")
    school_type = st.selectbox("학교 유형", ["일반 고등학교", "과학중점학교"])
    if st.button("🔄 초기화"): reset_all()

st.title("🏫 교육과정 정밀 점검 & PDF 리포트")

u_key = f"u_{st.session_state.get('uploader_key', 0)}"
uploaded_files = st.file_uploader("엑셀 파일 업로드", type=['xlsx'], accept_multiple_files=True, key=u_key)

if api_key and uploaded_files:
    model = get_model(api_key, school_type)
    
    if st.button("🔍 점검 시작", type="primary"):
        st.session_state.analysis_data = []
        for file in uploaded_files:
            with st.spinner(f"{file.name} 분석 중..."):
                result = analyze_excel(model, file)
                st.session_state.analysis_data.append(result)
        st.success("분석 완료!")

if st.session_state.analysis_data:
    st.divider()
    
    # 1. 개별 파일 결과 확인 및 PDF 다운로드
    for idx, data in enumerate(st.session_state.analysis_data):
        with st.expander(f"📄 {data['학교명']} 결과 보기"):
            st.table(pd.DataFrame(data['점검리포트']))
            st.info(data['종합의견'])
            
            # 개별 PDF 생성
            individual_pdf = create_pdf([data])
            st.download_button(
                label=f"📥 {data['학교명']} 리포트(PDF)",
                data=individual_pdf,
                file_name=f"{data['학교명']}_점검결과.pdf",
                mime="application/pdf",
                key=f"dl_{idx}"
            )

    st.divider()
    
    # 2. 통합 PDF 다운로드
    all_pdf = create_pdf(st.session_state.analysis_data)
    st.download_button(
        label="📥 모든 학교 통합 리포트(PDF) 다운로드",
        data=all_pdf,
        file_name="전체_교육과정_점검보고서.pdf",
        mime="application/pdf",
        use_container_width=True,
        type="primary"
    )
