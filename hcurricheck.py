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

# --- 2. 점검 지침 정의 (계산 로직 고도화) ---

CALCULATION_LOGIC = """
[학점 계산 및 검증 핵심 지침 - 매우 중요]
1. 학기별 총 이수 학점 계산: 
   - (학교 지정 과목 학점 합계) + (선택 과목 배정 학점 합계) + (창의적 체험활동 학점)을 모두 합산해야 함.
2. 선택 과목 학점 추출: 
   - '12(택3)'와 같은 형식에서 괄호 앞의 숫자 '12'가 해당 학기 배정 학점이므로 이를 합계에 사용함. 괄호 안의 숫자는 무시함.
3. 창의적 체험활동(창체): 
   - 시트 하단에 별도로 기재된 '창의적 체험활동', '자율/동아리/봉사/진로' 등의 학점을 반드시 찾아내어 각 학기 합계에 합산함. (보통 학기당 3학점 내외)
4. 결과 출력: 상세근거에 "1-1학기: 지정(22)+선택(7)+창체(3)=32학점"과 같이 계산 과정을 명시함.
"""

GENERAL_RULES = f"""
{CALCULATION_LOGIC}
[일반 지침]
1.총이수학점(192이상), 2.필수이수학점(84이상), 3.학기단위완결성(학기별 합계 확인), 
4.공통과목우선편성, 5.과목위계성(로마자 I, II 과목만 해당), 6.학기간학점균형(격차5이내), 
7.초과이수적정성, 8.과목별학점범위준수, 9.교과군별필수충족, 10.2022개정과목사용, 
11.국수영총합(81이내), 12.한국사(각3학점), 13.체육(10학점이상/매학기), 
14.종교과목선택권, 15.동일과목동일학점, 16.과목명확성, 17.기록형식준수
"""

SCIENCE_CORE_RULES = """
[과학중점학교 추가 지침]
18.1학년과정: 과학 10학점 편성(통합과학8+과탐실2)
19.과학선택과목: 물/화/생/지 I, II 8개 과목 개설 여부
20.수학선택과목: 미적분II, 기하 등 심화과목 필수 편성
21.정보교과: 정보 및 AI 관련 과목 편성
22.융합과목: 과학/수학 융합 선택 과목 편성
"""

# --- 3. 모델 설정 함수 (404 에러 방지 로직) ---

def get_model(api_key, school_type):
    try:
        genai.configure(api_key=api_key)
        
        # 사용 가능한 모델 리스트 확인
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # flash 모델 우선 선택 (이름 형식 대응)
        target_model = ""
        for m in ["models/gemini-1.5-flash", "gemini-1.5-flash", "models/gemini-pro"]:
            if m in available_models:
                target_model = m
                break
        
        if not target_model:
            target_model = available_models[0] # 최후의 수단으로 첫 번째 모델 선택

        rules = GENERAL_RULES
        if school_type == "과학중점학교":
            rules += "\n" + SCIENCE_CORE_RULES
        
        instruction = f"""
        당신은 대한민국 고등학교 교육과정 전문가입니다. 
        제공된 엑셀 데이터를 정밀 분석하여 점검 리포트를 JSON 형식으로 응답하세요.
        {rules}
        [응답 형식]
        {{"학교명": "", "점검리포트": [{{"항목": "항목명", "판정": "O/X", "상세근거": ""}}], "종합의견": ""}}
        """
        
        return genai.GenerativeModel(model_name=target_model, system_instruction=instruction)
    except Exception as e:
        st.error(f"모델 설정 중 오류 발생: {str(e)}")
        return None

# --- 4. 분석 실행 함수 ---

def analyze_excel(model, file):
    try:
        all_sheets = pd.read_excel(file, sheet_name=None)
        content = ""
        for name, df in all_sheets.items():
            df_cleaned = df.fillna("") # NaN 값 제거
            content += f"\n### 시트명: {name} ###\n{df_cleaned.to_csv(index=False)}\n"
        
        # 모델 호출 (프롬프트 전달)
        response = model.generate_content(
            f"파일명: {file.name}\n"
            f"이 데이터에서 학기별 학점(지정+선택+창체)을 정확히 계산하여 리포트를 작성하세요.\n"
            f"데이터:\n{content}"
        )
        
        # JSON 파싱
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_text)
    except Exception as e:
        return {"오류": f"분석 중 에러 발생: {str(e)}"}

# --- 5. UI 구성 ---

st.title("🏫 고등학교 교육과정 정밀 점검 시스템")

with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Gemini API Key", type="password")
    school_type = st.selectbox("학교 유형 선택", ["일반 고등학교", "과학중점학교"])
    st.divider()
    if st.button("🔄 전체 초기화"): reset_all()

# 세션 상태에서 안전하게 키 가져오기
current_uploader_key = f"u_{st.session_state.get('uploader_key', 0)}"
uploaded_files = st.file_uploader("엑셀 파일(.xlsx) 업로드", type=['xlsx'], accept_multiple_files=True, key=current_uploader_key)

if api_key and uploaded_files:
    model = get_model(api_key, school_type)
    
    if model and st.button("🔍 점검 시작", type="primary", use_container_width=True):
        st.session_state.analysis_data = []
        progress_bar = st.progress(0)
        
        for idx, file in enumerate(uploaded_files):
            st.write(f"⏳ {file.name} 분석 중... (지정+선택+창체 합산 수행 중)")
            result = analyze_excel(model, file)
            
            if "학교명" in result:
                st.session_state.analysis_data.append(result)
            else:
                st.error(f"{file.name} 분석 실패: {result.get('오류', '알 수 없는 오류')}")
            
            progress_bar.progress((idx + 1) / len(uploaded_files))
            time.sleep(2) # rate limit 방지
            
        if st.session_state.analysis_data:
            st.success("점검 완료!")

# --- 6. 결과 전시 및 내보내기 ---

if st.session_state.analysis_data:
    st.divider()
    school_names = [d.get('학교명', '알 수 없는 학교') for d in st.session_state.analysis_data]
    selected_school = st.selectbox("점검 결과 확인", school_names)
    
    curr = next(d for d in st.session_state.analysis_data if d.get('학교명') == selected_school)
    
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader(f"📊 {selected_school} 점검표")
        st.table(pd.DataFrame(curr['점검리포트']))
    with col2:
        st.subheader("💡 종합 개선 사항")
        st.info(curr['종합의견'])

    # 엑셀 다운로드 파일 생성
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        final_list = []
        for data in st.session_state.analysis_data:
            final_list.append(["학교명", data.get('학교명', ''), ""])
            final_list.append(["항목명", "판정", "상세근거"])
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
