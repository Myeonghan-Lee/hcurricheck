import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import io
import time

# --- 1. 앱 설정 및 세션 상태 초기화 ---
st.set_page_config(page_title="고등학교 교육과정 정밀 점검 시스템", layout="wide")

if 'analysis_data' not in st.session_state:
    st.session_state.analysis_data = None
if 'analysis_opinions' not in st.session_state:
    st.session_state.analysis_opinions = {}
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

def reset_all():
    st.session_state.analysis_data = None
    st.session_state.analysis_opinions = {}
    st.session_state.uploader_key += 1
    st.rerun()

def reset_analysis():
    st.session_state.analysis_data = None
    st.session_state.analysis_opinions = {}
    st.rerun()

# --- 2. 시스템 인스트럭션 ---
CHECK_ITEMS = [
    "1.총이수학점(192이상)", "2.필수이수학점(84이상)", "3.학기단위완결성", "4.공통과목우선편성",
    "5.과목위계성(Ⅰ→Ⅱ)", "6.학기간학점균형(격차5이내)", "7.초과이수적정성", "8.과목별학점범위준수",
    "9.교과군별필수충족", "10.2022개정과목사용", "11.국수영총합(81이내)", "12.한국사(각3학점)",
    "13.체육(10학점이상/매학기)", "14.종교과목선택권", "15.동일과목동일학점", "16.과목명확성(오탈자)",
    "17.기록형식준수(<4(2)>)"
]

SYSTEM_INSTRUCTION = f"""
당신은 대한민국 고등학교 교육과정 전문가입니다. 제공된 엑셀 데이터를 바탕으로 아래 17개 항목을 점검하세요.
항목명: {", ".join(CHECK_ITEMS)}

[특이사항]
- 과목명 뒤에 공백(Space)이 있는 것은 정상이며 오류로 판정하지 마십시오.

[응답 규칙]
1. 각 항목별 판정(O/X/△)과 상세근거를 분리하여 JSON으로 응답하세요.
2. 반드시 아래 JSON 형식으로만 응답하세요.

{{
    "학교명": "학교이름",
    "점검리포트": [
        {{ "항목": "1.총이수학점(192이상)", "판정": "O", "상세근거": "내용" }},
        ...
    ],
    "종합의견": "상세 서술"
}}
"""

# --- 3. 모델 초기화 및 분석 함수 (404 에러 방지 최적화) ---

def get_stable_model(api_key):
    try:
        genai.configure(api_key=api_key)
        # 현재 API 키로 접근 가능한 모델 목록 탐색
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # 모델 우선순위 리스트 (경로 포함/미포함 모두 대응)
        target_names = ['models/gemini-1.5-flash', 'gemini-1.5-flash', 'models/gemini-1.5-pro']
        
        selected_model_name = None
        for target in target_names:
            if target in available_models:
                selected_model_name = target
                break
        
        if not selected_model_name and available_models:
            selected_model_name = available_models[0]
            
        if selected_model_name:
            return genai.GenerativeModel(model_name=selected_model_name, system_instruction=SYSTEM_INSTRUCTION)
        return None
    except:
        return None

def analyze_excel(model, file):
    try:
        all_sheets = pd.read_excel(file, sheet_name=None)
        content = ""
        for name, df in all_sheets.items():
            content += f"\n[시트: {name}]\n{df.to_csv(index=False)}"
        
        response = model.generate_content(f"파일명: {file.name}\n데이터:\n{content}")
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(clean_text)
        
        rows = []
        for item in data.get('점검리포트', []):
            rows.append({
                "학교명": data.get('학교명', '알 수 없음'),
                "항목명": item.get('항목', '항목미상'),
                "판정": item.get('판정', '-'),
                "상세근거": item.get('상세근거', '-')
            })
        return rows, data.get('학교명', '알 수 없음'), data.get('종합의견', '의견 없음')
    except Exception as e:
        return None, None, f"에러: {str(e)}"

# --- 4. UI 레이아웃 ---

st.title("🏫 2027 고등학교 교육과정 정밀 점검 도구")
st.caption("안정성이 강화된 교육과정 자동 점검 시스템입니다.")

with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Gemini API Key", type="password")
    st.divider()
    if st.button("🔄 전체 초기화", use_container_width=True): reset_all()
    if st.button("🧹 결과만 삭제", use_container_width=True): reset_analysis()

uploaded_files = st.file_uploader(
    "점검할 엑셀 파일(.xlsx)을 업로드하세요", 
    type=['xlsx'], 
    accept_multiple_files=True,
    key=f"uploader_{st.session_state.uploader_key}"
)

if api_key and uploaded_files:
    model = get_stable_model(api_key)
    
    if model and st.button("🔍 점검 시작", type="primary", use_container_width=True):
        all_data_rows = []
        all_opinions = {}
        progress_bar = st.progress(0)
        
        for idx, file in enumerate(uploaded_files):
            st.write(f"⏳ **{file.name}** 분석 중...")
            rows, s_name, opinion = analyze_excel(model, file)
            
            if rows:
                all_data_rows.extend(rows)
                all_opinions[s_name] = opinion
            else:
                st.error(f"{file.name} 분석 실패: {opinion}")
            
            progress_bar.progress((idx + 1) / len(uploaded_files))
            time.sleep(12)
            
        if all_data_rows:
            st.session_state.analysis_data = pd.DataFrame(all_data_rows)
            st.session_state.analysis_opinions = all_opinions
            st.success("✅ 모든 분석이 완료되었습니다!")
        else:
            st.error("분석된 데이터가 없습니다. 파일을 확인해 주세요.")

# --- 5. 결과 표시 (KeyError 방지 로직 포함) ---

if st.session_state.analysis_data is not None and not st.session_state.analysis_data.empty:
    st.divider()
    
    # 컬럼 존재 여부 체크
    if '학교명' in st.session_state.analysis_data.columns:
        school_list = st.session_state.analysis_data['학교명'].unique()
        target_school = st.selectbox("📝 점검 결과 확인 학교 선택", school_list)
        
        school_df = st.session_state.analysis_data[st.session_state.analysis_data['학교명'] == target_school].reset_index(drop=True)
        
        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader(f"📊 {target_school} 결과")
            st.table(school_df[['항목명', '판정', '상세근거']])
        with c2:
            st.subheader("💡 종합 개선 사항")
            st.info(st.session_state.analysis_opinions.get(target_school, "의견 없음"))

        # 다운로드
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            st.session_state.analysis_data.to_excel(writer, index=False, sheet_name='점검결과')
            opinion_df = pd.DataFrame([{"학교명": k, "종합의견": v} for k, v in st.session_state.analysis_opinions.items()])
            opinion_df.to_excel(writer, index=False, sheet_name='종합개선사항')
        
        st.download_button("📥 통합 결과(Excel) 다운로드", output.getvalue(), "교육과정_점검결과.xlsx", use_container_width=True)
    else:
        st.error("분석 데이터 구조에 오류가 있습니다.")
else:
    if not api_key: st.warning("👈 사이드바에 API 키를 입력하세요.")
