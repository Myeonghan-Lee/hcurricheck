import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import io
import time

# --- 1. 앱 설정 및 세션 상태 초기화 ---
st.set_page_config(page_title="고등학교 교육과정 정밀 점검 시스템", layout="wide")

# 세션 상태 변수 초기화 (결과 데이터 및 종합 의견 저장)
if 'analysis_data' not in st.session_state:
    st.session_state.analysis_data = None  # 상세 테이블 데이터
if 'analysis_opinions' not in st.session_state:
    st.session_state.analysis_opinions = {} # 학교별 종합 의견
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# 초기화 함수
def reset_all():
    st.session_state.analysis_data = None
    st.session_state.analysis_opinions = {}
    st.session_state.uploader_key += 1
    st.rerun()

def reset_analysis():
    st.session_state.analysis_data = None
    st.session_state.analysis_opinions = {}
    st.rerun()

# --- 2. 시스템 인스트럭션 (지침 데이터 최적화) ---
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

[특이사항 준수]
- **과목명 뒤에 공백(Space)이 있는 것은 정상적인 것으로 간주하며, 이를 '과목명확성' 오류로 판정하지 마십시오.**

[응답 규칙]
1. 각 항목에 대해 '판정(O/X/△)'과 '상세근거'를 반드시 분리하여 응답하세요.
2. 반드시 아래 JSON 형식으로만 응답하세요.

[응답 JSON 형식]
{{
    "학교명": "학교이름",
    "점검리포트": [
        {{ "항목": "1.총이수학점(192이상)", "판정": "O", "상세근거": "총 192학점 편성 확인됨" }},
        ... (17개 항목 반복)
    ],
    "종합의견": "이 학교 교육과정에 대한 종합적인 분석 결과와 개선이 필요한 구체적인 사항들을 서술형으로 작성하세요."
}}
"""

# --- 3. 모델 및 분석 함수 ---

def init_model(api_key):
    try:
        genai.configure(api_key=api_key)
        # 404 에러 방지를 위해 models/ 접두사 명시
        model = genai.GenerativeModel(
            model_name='models/gemini-1.5-flash', 
            system_instruction=SYSTEM_INSTRUCTION
        )
        return model
    except: return None

def analyze_excel(model, file):
    try:
        all_sheets = pd.read_excel(file, sheet_name=None)
        content = ""
        for name, df in all_sheets.items():
            content += f"\n[시트: {name}]\n{df.to_csv(index=False)}"
        
        response = model.generate_content(f"파일명: {file.name}\n데이터:\n{content}")
        # AI가 출력한 마크다운 태그 제거 후 JSON 로드
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(clean_text)
        
        rows = []
        for item in data['점검리포트']:
            rows.append({
                "학교명": data['학교명'],
                "항목명": item['항목'],
                "판정": item['판정'],
                "상세근거": item['상세근거']
            })
        return rows, data['학교명'], data['종합의견']
    except Exception as e:
        return None, None, f"분석 오류 발생: {str(e)}"

# --- 4. 메인 UI 레이아웃 ---

st.title("🏫 2027 고등학교 교육과정 정밀 점검 도구")
st.caption("2022 개정 교육과정 지침 및 서울특별시교육청 편성·운영 방향을 기반으로 자동 점검합니다.")

with st.sidebar:
    st.header("⚙️ 설정 및 도구")
    api_key = st.text_input("Gemini API Key", type="password")
    st.divider()
    if st.button("🔄 전체 초기화 (파일+결과)", use_container_width=True):
        reset_all()
    if st.button("🧹 분석 결과만 삭제", use_container_width=True):
        reset_analysis()

# 파일 업로드 영역
uploaded_files = st.file_uploader(
    "점검할 교육과정 엑셀 파일(.xlsx)을 업로드하세요", 
    type=['xlsx'], 
    accept_multiple_files=True,
    key=f"uploader_{st.session_state.uploader_key}"
)

if api_key and uploaded_files:
    model = init_model(api_key)
    
    # [수정 포인트] color="primary" -> type="primary"
    if st.button("🔍 점검 시작", type="primary", use_container_width=True):
        all_data_rows = []
        all_opinions = {}
        progress_bar = st.progress(0)
        
        for idx, file in enumerate(uploaded_files):
            st.write(f"⏳ **{file.name}** 분석 중...")
            rows, school_name, opinion = analyze_excel(model, file)
            
            if rows:
                all_data_rows.extend(rows)
                all_opinions[school_name] = opinion
            else:
                st.error(f"{file.name} 분석 실패: {opinion}")
            
            progress_bar.progress((idx + 1) / len(uploaded_files))
            time.sleep(12) # 무료 할당량(RPM) 준수
            
        st.session_state.analysis_data = pd.DataFrame(all_data_rows)
        st.session_state.analysis_opinions = all_opinions
        st.success("✅ 모든 분석이 완료되었습니다!")

# --- 5. 결과 표시 영역 ---

if st.session_state.analysis_data is not None:
    st.divider()
    
    # 학교 선택 필터
    res_df = st.session_state.analysis_data
    school_list = res_df['학교명'].unique()
    target_school = st.selectbox("📝 점검 결과를 확인할 학교를 선택하세요", school_list)
    
    # 선택된 학교의 데이터 추출
    school_df = res_df[res_df['학교명'] == target_school].reset_index(drop=True)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader(f"📊 {target_school} 항목별 점검 결과")
        st.table(school_df[['항목명', '판정', '상세근거']])
    
    with col2:
        st.subheader("💡 종합 개선 사항")
        # [기능 추가] 종합 의견(개선 사항) 표시
        opinion_text = st.session_state.analysis_opinions.get(target_school, "의견을 불러올 수 없습니다.")
        st.info(opinion_text)

    # 전체 결과 엑셀 다운로드
    st.divider()
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        res_df.to_excel(writer, index=False, sheet_name='점검결과_통합')
        # 의견 시트 따로 추가
        opinion_df = pd.DataFrame([{"학교명": k, "종합의견": v} for k, v in st.session_state.analysis_opinions.items()])
        opinion_df.to_excel(writer, index=False, sheet_name='종합개선사항')
    
    st.download_button(
        label="📥 통합 점검 결과 및 개선사항(Excel) 다운로드",
        data=output.getvalue(),
        file_name="교육과정_점검결과_통합본.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
    
else:
    if not api_key:
        st.warning("👈 사이드바에 API 키를 입력해 주세요.")
    elif not uploaded_files:
        st.info("📂 엑셀 파일을 업로드한 후 '점검 시작' 버튼을 눌러주세요.")
