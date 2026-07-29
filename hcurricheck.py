import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import io
import time

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

# --- 2. 점검 지침 정의 (요구사항 반영 고도화) ---

CALCULATION_LOGIC = """
[학점 계산 및 검증 정밀 지침]
1. [x] 기호 처리: 
   - 대괄호 안에 들어있는 숫자(예: [4])는 합산에서 반드시 제외할 것. 
   - 이는 분반 운영(1학기/2학기 교차 이수)을 의미하므로 중복 합산을 방지해야 함.

2. 학기별 총합 계산: 
   - (학교 지정 학점) + (선택 과목 배정 학점) + (창의적 체험활동 학점)을 더함. 
   - 단, 선택 과목은 '12(택3)'에서 괄호 앞의 숫자 '12'를 사용함.

3. 필수이수학점(84학점) 및 교과군별 검증:
   - 각 교과군(국, 수, 영, 사, 과, 체, 예) 및 (기/가/정/외/한/교)의 이수학점을 검토할 때 아래 공식을 따름.
   - 공식: {교과군별 총 학점} = {학교 지정 학점} + {해당 교과군 내 학생 선택 필수 최소 학점}
   - 국(10), 수학(10), 영어(10), 사회(10), 과학(12), 체육(10), 예술(10) 충족 여부 확인.
   - 기술·가정/정보/제2외국어/한문/교양 교과군은 모두 합쳐서 '16학점' 이상인지 확인.

4. 결과 출력: 
   - 상세근거에 교과군별 합산 내역을 명시할 것. (예: 사회: 지정(6)+선택 최소(4)=10학점 -> 충족)
"""

GENERAL_RULES = f"""
{CALCULATION_LOGIC}
[일반 지침]
1.총이수학점(192이상), 2.필수이수학점(84이상), 3.학기단위완결성, 4.공통과목우선편성, 
5.과목위계성(로마자 I, II 과목), 6.학기간학점균형(격차5이내), 7.초과이수적정성, 
8.과목별학점범위준수, 9.교과군별필수충족(8개 교과군), 10.2022개정과목사용, 
11.국수영총합(81이내), 12.한국사(각3학점), 13.체육(매학기 편성), 
14.종교과목선택권, 15.동일과목동일학점, 16.과목명확성, 17.기록형식준수
"""

SCIENCE_CORE_RULES = """
[과학중점학교 추가 지침]
18.1학년과정: 과학 10학점 편성(통합과학8+과탐실2)
19.과학선택과목: 물/화/생/지 I, II 8개 과목 개설
20.수학선택과목: 미적분II, 기하 등 심화과목 편성
21.정보교과: 정보 및 AI 관련 과목 필수 편성
22.융합과목: 과학/수학 융합 선택 과목 편성
"""

# --- 3. 모델 설정 함수 (모델 리스트 자동 확인 포함) ---

def get_model(api_key, school_type):
    try:
        genai.configure(api_key=api_key)
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        target_model = "models/gemini-1.5-flash" 
        if target_model not in available_models:
            # 모델명이 다를 경우 대체 시도
            target_model = next((m for m in available_models if "flash" in m), available_models[0])

        rules = GENERAL_RULES
        if school_type == "과학중점학교":
            rules += "\n" + SCIENCE_CORE_RULES
        
        instruction = f"""
        당신은 대한민국 고등학교 교육과정 편성표 분석 전문가입니다.
        제시된 엑셀 데이터를 바탕으로 교육과정 지침 위반 여부를 점검하여 JSON으로 응답하세요.
        {rules}
        
        [응답 규칙]
        - 반드시 JSON 형식을 유지할 것.
        - '상세근거'에 [x] 제외 여부와 교과군별 합산(지정+선택최소) 과정을 상세히 기록할 것.
        - JSON: {{"학교명": "", "점검리포트": [{{"항목": "", "판정": "", "상세근거": ""}}], "종합의견": ""}}
        """
        return genai.GenerativeModel(model_name=target_model, system_instruction=instruction)
    except Exception as e:
        st.error(f"모델 초기화 오류: {str(e)}")
        return None

# --- 4. 분석 실행 함수 ---

def analyze_excel(model, file):
    try:
        all_sheets = pd.read_excel(file, sheet_name=None)
        content = ""
        for name, df in all_sheets.items():
            df_cleaned = df.fillna("")
            content += f"\n### 시트명: {name} ###\n{df_cleaned.to_csv(index=False)}\n"
        
        prompt = f"""
        파일명: {file.name}
        데이터를 분석하여 리포트를 작성하세요. 
        특히 대괄호 [ ] 숫자를 제외하고 계산하는 것과 교과군별 '학교지정+선택최소' 합산 로직을 엄격히 적용하세요.
        
        데이터:
        {content}
        """
        response = model.generate_content(prompt)
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_text)
    except Exception as e:
        return {"오류": f"분석 중 에러: {str(e)}"}

# --- 5. UI 구성 (생략 없이 완성본 제공) ---

st.title("🏫 고등학교 교육과정 정밀 점검 시스템")

with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Gemini API Key", type="password")
    school_type = st.selectbox("학교 유형 선택", ["일반 고등학교", "과학중점학교"])
    st.divider()
    if st.button("🔄 전체 초기화"): reset_all()

u_key = f"u_{st.session_state.get('uploader_key', 0)}"
uploaded_files = st.file_uploader("엑셀 파일(.xlsx) 업로드", type=['xlsx'], accept_multiple_files=True, key=u_key)

if api_key and uploaded_files:
    model = get_model(api_key, school_type)
    
    if model and st.button("🔍 점검 시작", type="primary", use_container_width=True):
        st.session_state.analysis_data = []
        progress_bar = st.progress(0)
        
        for idx, file in enumerate(uploaded_files):
            st.write(f"⏳ {file.name} 분석 중 (교과군별 필수 학점 검증...)")
            result = analyze_excel(model, file)
            
            if "학교명" in result:
                st.session_state.analysis_data.append(result)
            else:
                st.error(f"{file.name} 실패: {result.get('오류')}")
            
            progress_bar.progress((idx + 1) / len(uploaded_files))
            time.sleep(1)
            
        if st.session_state.analysis_data:
            st.success("분석이 완료되었습니다!")

# --- 6. 결과 전시 및 내보내기 ---

if st.session_state.analysis_data:
    st.divider()
    school_names = [d.get('학교명', '알 수 없는 학교') for d in st.session_state.analysis_data]
    selected_school = st.selectbox("결과 확인 대상 학교", school_names)
    
    curr = next(d for d in st.session_state.analysis_data if d.get('학교명') == selected_school)
    
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader(f"📊 {selected_school} 점검 리포트")
        st.table(pd.DataFrame(curr['점검리포트']))
    with col2:
        st.subheader("💡 종합 의견")
        st.info(curr['종합의견'])

    # 엑셀 다운로드 파일 생성
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        final_list = []
        for data in st.session_state.analysis_data:
            final_list.append(["학교명", data.get('학교명', ''), ""])
            final_list.append(["항목", "판정", "상세근거"])
            for item in data.get('점검리포트', []):
                final_list.append([item.get('항목', ''), item.get('판정', ''), item.get('상세근거', '')])
            final_list.append(["종합개선사항", "", data.get('종합의견', '')])
            final_list.append(["", "", ""]) 
        pd.DataFrame(final_list).to_excel(writer, index=False, header=False, sheet_name='점검결과')
    
    st.download_button(
        label="📥 점검 결과 보고서(Excel) 다운로드",
        data=output.getvalue(),
        file_name=f"교육과정_점검보고서_{school_type}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
