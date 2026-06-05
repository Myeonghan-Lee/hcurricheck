import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import io
import time

# --- 1. 앱 설정 및 세션 초기화 ---
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

# --- 2. 시스템 인스트럭션 (지침 고도화) ---
CHECK_ITEMS = [
    "1.총이수학점(192이상)", "2.필수이수학점(84이상)", "3.학기단위완결성", "4.공통과목우선편성",
    "5.과목위계성(Ⅰ→Ⅱ)", "6.학기간학점균형(격차5이내)", "7.초과이수적정성", "8.과목별학점범위준수",
    "9.교과군별필수충족", "10.2022개정과목사용", "11.국수영총합(81이내)", "12.한국사(각3학점)",
    "13.체육(10학점이상/매학기)", "14.종교과목선택권", "15.동일과목동일학점", "16.과목명확성(오탈자)",
    "17.기록형식준수"
]

SYSTEM_INSTRUCTION = f"""
당신은 대한민국 고등학교 교육과정 전문가입니다. 제공된 엑셀 데이터를 바탕으로 아래 17개 항목을 점검하세요.
항목명: {", ".join(CHECK_ITEMS)}

[특이사항 및 17번 항목 지침]
- 과목명 뒤의 공백(Space)은 정상이며 오류로 판정하지 마십시오.
- **17.기록형식준수 점검:** 엑셀 상에서 학점(예: 12)과 선택 정보(예: (택4))가 위아래 두 줄(줄바꿈)로 표현된 경우, 이를 '12(택4)' 형식으로 해석하여 지침 준수 여부를 판단하십시오. 

[응답 규칙]
1. 각 항목별 판정(O/X/△)과 상세근거를 분리하여 JSON으로 응답하세요.
2. **'종합의견'은 반드시 개조식(Bullet point, 예: - 내용)으로 작성하십시오.**
3. 반드시 아래 JSON 형식으로만 응답하세요.

{{
    "학교명": "학교이름",
    "점검리포트": [
        {{ "항목": "1.총이수학점(192이상)", "판정": "O", "상세근거": "내용" }},
        ...
    ],
    "종합의견": "- 첫 번째 제언\\n- 두 번째 제언\\n- 세 번째 제언"
}}
"""

# --- 3. 모델 및 분석 로직 (안정성 강화) ---

def get_stable_model(api_key):
    try:
        genai.configure(api_key=api_key)
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        target_names = ['models/gemini-1.5-flash', 'gemini-1.5-flash', 'models/gemini-1.5-pro']
        selected = next((t for t in target_names if t in available), available[0] if available else None)
        return genai.GenerativeModel(model_name=selected, system_instruction=SYSTEM_INSTRUCTION) if selected else None
    except: return None

def analyze_excel(model, file):
    try:
        all_sheets = pd.read_excel(file, sheet_name=None)
        content = ""
        for name, df in all_sheets.items():
            content += f"\n[시트: {name}]\n{df.to_csv(index=False)}"
        
        response = model.generate_content(f"파일명: {file.name}\n데이터:\n{content}")
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(clean_text)
        
        opinion = data.get('종합의견', '의견 없음')
        rows = []
        for item in data.get('점검리포트', []):
            rows.append({
                "학교명": data.get('학교명', '알 수 없음'),
                "항목명": item.get('항목', '항목미상'),
                "판정": item.get('판정', '-'),
                "상세근거": item.get('상세근거', '-'),
                "종합개선사항": opinion # 엑셀 내보내기 시 포함되도록 각 행에 추가
            })
        return rows, data.get('학교명', '알 수 없음'), opinion
    except Exception as e:
        return None, None, f"에러: {str(e)}"

# --- 4. 사용자 인터페이스 ---

st.title("🏫 2027 고등학교 교육과정 정밀 점검 도구")
st.caption("17개 항목 전수 점검 및 개조식 개선 제언 시스템")

with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Gemini API Key", type="password")
    if st.button("🔄 전체 초기화", use_container_width=True): reset_all()

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
        progress = st.progress(0)
        
        for idx, file in enumerate(uploaded_files):
            st.write(f"⏳ **{file.name}** 분석 중...")
            rows, s_name, opinion = analyze_excel(model, file)
            if rows:
                all_data_rows.extend(rows)
                all_opinions[s_name] = opinion
            else:
                st.error(f"{file.name} 분석 실패: {opinion}")
            progress.progress((idx + 1) / len(uploaded_files))
            time.sleep(12)
            
        if all_data_rows:
            st.session_state.analysis_data = pd.DataFrame(all_data_rows)
            st.session_state.analysis_opinions = all_opinions
            st.success("✅ 모든 분석이 완료되었습니다!")

# --- 5. 결과 표시 및 내보내기 ---

if st.session_state.analysis_data is not None and not st.session_state.analysis_data.empty:
    st.divider()
    res_df = st.session_state.analysis_data
    
    if '학교명' in res_df.columns:
        school_list = res_df['학교명'].unique()
        target_school = st.selectbox("📝 점검 결과 확인 학교 선택", school_list)
        
        school_df = res_df[res_df['학교명'] == target_school].reset_index(drop=True)
        
        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader(f"📊 {target_school} 점검 결과")
            # 화면에는 종합개선사항 컬럼을 제외하고 표시
            st.table(school_df[['항목명', '판정', '상세근거']])
        with c2:
            st.subheader("💡 종합 개선 사항 (개조식)")
            st.info(st.session_state.analysis_opinions.get(target_school, "의견 없음"))

        # 엑셀 다운로드 (종합개선사항 컬럼 포함)
        st.divider()
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # 1. 통합 결과 시트 (모든 항목 + 개선사항 포함)
            res_df.to_excel(writer, index=False, sheet_name='전체_점검_결과')
            
            # 2. 개선사항 전용 시트 (학교별 요약)
            opinion_df = pd.DataFrame([
                {"학교명": k, "종합개선사항": v} for k, v in st.session_state.analysis_opinions.items()
            ])
            opinion_df.to_excel(writer, index=False, sheet_name='학교별_개선사항_요약')
            
        st.download_button(
            label=f"📥 {target_school} 포함 통합 결과(Excel) 다운로드", 
            data=output.getvalue(), 
            file_name="교육과정_점검_및_개선사항_결과.xlsx", 
            use_container_width=True
        )
else:
    if not api_key: st.warning("👈 사이드바에 API 키를 입력하세요.")
