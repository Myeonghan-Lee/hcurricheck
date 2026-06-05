import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import io
import time
from PIL import Image

# --- 1. 앱 설정 ---
st.set_page_config(page_title="고등학교 교육과정 정밀 점검 시스템", layout="wide")

if 'analysis_data' not in st.session_state:
    st.session_state.analysis_data = []
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

def reset_all():
    st.session_state.analysis_data = []
    st.session_state.uploader_key += 1
    st.rerun()

# --- 2. 점검 지침 정의 ---
# 일반고 지침 (17개)
GENERAL_RULES = """
[일반 지침]
1.총이수학점(192이상), 2.필수이수학점(84이상), 3.학기단위완결성, 4.공통과목우선편성, 
5.과목위계성(로마자 Ⅰ, Ⅱ 포함 과목만 대상. 한국사1, 2 등 아라비아 숫자는 제외), 
6.학기간학점균형(격차5이내), 7.초과이수적정성, 8.과목별학점범위준수(공통3~4, 한국사3, 과탐실1, 선택3~5, 예체능/교양2~4, 스포츠/생애1~2), 
9.교과군별필수충족, 10.2022개정과목사용, 11.국수영총합(81이내), 12.한국사(각3학점), 
13.체육(10학점이상/매학기), 14.종교과목선택권, 15.동일과목동일학점, 16.과목명확성(공백허용), 
17.기록형식준수(엑셀 두 줄 표기 '학점/(택O)'를 '학점(택O)'로 해석)
"""

# 과학중점학교 추가 지침 (5개)
SCIENCE_CORE_RULES = """
[과학중점학교 추가 지침]
18.1학년과정: 과학 교과(통합과학1,2, 과탐실1,2) 총 10학점 편성 여부
19.과학선택과목: 물리학, 화학, 생명과학, 지구과학 4개 일반선택과 그에 따른 진로선택과목(역학과 에너지 등)이 다양하게 개설되었는가
20.수학선택과목: 대수, 미적분Ⅰ, 확통(일반) 및 기하, 미적분Ⅱ(진로) 등이 체계적으로 편성되었는가
21.정보교과: 정보(일반) 및 인공지능 기초, 데이터 과학 등 정보 관련 과목이 편성되었는가
22.융합과목권장: 과학의 역사와 문화, 기후변화, 수학과 문화 등 융합 선택 과목 편성 여부
"""

# --- 3. 모델 설정 함수 ---

def get_model(api_key, school_type):
    genai.configure(api_key=api_key)
    rules = GENERAL_RULES
    if school_type == "과학중점학교":
        rules += "\n" + SCIENCE_CORE_RULES
    
    instruction = f"""
    당신은 대한민국 고등학교 교육과정 전문가입니다. 아래 지침에 따라 교육과정을 점검하고 JSON으로 응답하세요.
    {rules}
    
    [응답 규칙]
    - 종합 의견은 반드시 개조식(- 사용)으로 작성하십시오.
    - JSON 형식: {{"학교명": "", "점검리포트": [{{"항목": "항목명", "판정": "O/X", "상세근거": ""}}], "종합의견": ""}}
    """
    
    available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    target = next((t for t in ['models/gemini-1.5-flash', 'gemini-1.5-flash'] if t in available), available[0])
    return genai.GenerativeModel(model_name=target, system_instruction=instruction)

# --- 4. 분석 실행 함수 ---

def analyze_excel(model, file):
    try:
        all_sheets = pd.read_excel(file, sheet_name=None)
        content = ""
        for name, df in all_sheets.items():
            content += f"\n[시트: {name}]\n{df.to_csv(index=False)}"
        
        response = model.generate_content(f"파일명: {file.name}\n데이터:\n{content}")
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_text)
    except Exception as e:
        return {"오류": str(e)}

# --- 5. UI 구성 ---

st.title("🏫 고등학교 교육과정 정밀 점검 시스템")

with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Gemini API Key", type="password")
    school_type = st.selectbox("학교 유형 선택", ["일반 고등학교", "과학중점학교"])
    st.divider()
    if st.button("🔄 전체 초기화"): reset_all()

uploaded_files = st.file_uploader("엑셀 파일(.xlsx) 업로드", type=['xlsx'], accept_multiple_files=True, key=f"u_{st.session_state.uploader_key}")

if api_key and uploaded_files:
    model = get_model(api_key, school_type)
    
    if st.button("🔍 점검 시작", type="primary", use_container_width=True):
        st.session_state.analysis_data = []
        progress_bar = st.progress(0)
        
        for idx, file in enumerate(uploaded_files):
            st.write(f"⏳ {file.name} ({school_type}) 분석 중...")
            result = analyze_excel(model, file)
            if "학교명" in result:
                st.session_state.analysis_data.append(result)
            else:
                st.error(f"{file.name} 분석 실패: {result.get('오류')}")
            
            progress_bar.progress((idx + 1) / len(uploaded_files))
            time.sleep(12)
        st.success("점검 완료!")

# --- 6. 결과 전시 및 내보내기 ---

if st.session_state.analysis_data:
    st.divider()
    school_names = [d['학교명'] for d in st.session_state.analysis_data]
    selected_school = st.selectbox("점검 결과 확인", school_names)
    
    curr = next(d for d in st.session_state.analysis_data if d['학교명'] == selected_school)
    
    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader(f"📊 {selected_school} 점검표")
        st.table(pd.DataFrame(curr['점검리포트']))
    with c2:
        st.subheader("💡 종합 개선 사항")
        st.info(curr['종합의견'])

    # --- 요구사항 반영 엑셀 생성 ---
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        final_list = []
        for data in st.session_state.analysis_data:
            final_list.append(["학교명", data['학교명'], ""])
            final_list.append(["항목명", "판정", "상세근거"])
            for item in data['점검리포트']:
                final_list.append([item['항목'], item['판정'], item['상세근거']])
            final_list.append(["종합개선사항", "", data['종합의견']])
            final_list.append(["", "", ""]) # 구분 빈 줄
            
        pd.DataFrame(final_list).to_excel(writer, index=False, header=False, sheet_name='점검결과보고서')
    
    st.download_button(
        label="📥 점검 결과 보고서(Excel) 다운로드",
        data=output.getvalue(),
        file_name=f"교육과정_점검보고서_{school_type}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
