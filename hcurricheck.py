import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import io
import time

# --- 1. 앱 설정 및 세션 상태 ---
st.set_page_config(page_title="고등학교 교육과정 정밀 점검 시스템", layout="wide")

if 'analysis_data' not in st.session_state:
    st.session_state.analysis_data = [] # 리스트 형태로 변경 (학교별 독립 구조)
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

def reset_all():
    st.session_state.analysis_data = []
    st.session_state.uploader_key += 1
    st.rerun()

# --- 2. 시스템 인스트럭션 (요구사항 반영) ---
SYSTEM_INSTRUCTION = """
당신은 대한민국 고등학교 교육과정 전문가입니다. 제공된 엑셀 데이터를 바탕으로 아래 17개 항목을 점검하세요.

[특수 점검 규칙]
1. **기록 형식(17번 항목):** 엑셀 셀 내에서 두 줄로 표현된 경우(첫 줄: 학점, 둘째 줄: (택O))는 '12(택4)'와 같은 형식으로 간주하여 지침 준수 여부를 검토하십시오.
2. **위계성(5번 항목):** 과목명에 'Ⅰ, Ⅱ, Ⅲ'과 같은 **로마자**가 포함된 경우에만 위계성 점검을 수행하십시오. '한국사1, 2'나 '공통수학1, 2'와 같이 **아라비아 숫자(1, 2)**가 포함된 과목은 위계성 점검 대상에서 제외하십시오.
3. **종합 의견:** 반드시 **개조식(Bullet point)**으로 작성하십시오.

[점검 항목]
1.총이수학점(192이상), 2.필수이수학점(84이상), 3.학기단위완결성, 4.공통과목우선편성, 5.과목위계성(로마자만), 
6.학기간학점균형(격차5이내), 7.초과이수적정성, 8.과목별학점범위준수, 9.교과군별필수충족, 10.2022개정과목사용, 
11.국수영총합(81이내), 12.한국사(각3학점), 13.체육(10학점이상/매학기), 14.종교과목선택권, 15.동일과목동일학점, 
16.과목명확성(오탈자/공백허용), 17.기록형식준수(학점(택O))

[응답 JSON 형식]
{
    "학교명": "학교이름",
    "점검리포트": [
        { "항목": "1.총이수학점(192이상)", "판정": "O", "상세근거": "근거 내용" },
        ... (17개 항목)
    ],
    "종합의견": "- 의견1\n- 의견2\n- 의견3"
}
"""

# --- 3. 모델 설정 및 분석 로직 ---

def get_stable_model(api_key):
    try:
        genai.configure(api_key=api_key)
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        target = next((t for t in ['models/gemini-1.5-flash', 'gemini-1.5-flash'] if t in available), available[0])
        return genai.GenerativeModel(model_name=target, system_instruction=SYSTEM_INSTRUCTION)
    except: return None

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

# --- 4. UI 및 실행 ---

st.title("🏫 고등학교 교육과정 정밀 점검 도구")

with st.sidebar:
    api_key = st.text_input("Gemini API Key", type="password")
    if st.button("🔄 전체 초기화", use_container_width=True): reset_all()

uploaded_files = st.file_uploader("엑셀 파일 업로드", type=['xlsx'], accept_multiple_files=True, key=f"u_{st.session_state.uploader_key}")

if api_key and uploaded_files:
    model = get_stable_model(api_key)
    if model and st.button("🔍 점검 시작", type="primary", use_container_width=True):
        st.session_state.analysis_data = [] # 결과 초기화
        progress_bar = st.progress(0)
        
        for idx, file in enumerate(uploaded_files):
            st.write(f"⏳ {file.name} 분석 중...")
            result = analyze_excel(model, file)
            if "학교명" in result:
                st.session_state.analysis_data.append(result)
            else:
                st.error(f"{file.name} 분석 실패: {result.get('오류')}")
            
            progress_bar.progress((idx + 1) / len(uploaded_files))
            time.sleep(12)
        st.success("점검 완료!")

# --- 5. 결과 표시 및 사용자 정의 엑셀 내보내기 ---

if st.session_state.analysis_data:
    st.divider()
    
    # 화면 표시 (학교별 선택)
    school_names = [d['학교명'] for d in st.session_state.analysis_data]
    selected_school = st.selectbox("확인할 학교 선택", school_names)
    
    curr_data = next(d for d in st.session_state.analysis_data if d['학교명'] == selected_school)
    
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader(f"📊 {selected_school} 점검 결과")
        st.table(pd.DataFrame(curr_data['점검리포트']))
    with col2:
        st.subheader("💡 종합 개선 사항")
        st.info(curr_data['종합의견'])

    # --- 사용자 정의 엑셀 생성 (요구사항 4 반영) ---
    output = io.BytesIO()
    workbook = pd.ExcelWriter(output, engine='openpyxl')
    
    # 모든 학교를 하나의 시트에 특정 양식으로 쌓기
    final_report_list = []
    for data in st.session_state.analysis_data:
        # 1. 학교명 줄
        final_report_list.append(["학교명", data['학교명'], ""])
        # 2. 항목명 줄
        final_report_list.append(["항목명", "판정", "상세근거"])
        # 3. 데이터 줄
        for item in data['점검리포트']:
            final_report_list.append([item['항목'], item['판정'], item['상세근거']])
        # 4. 종합개선사항 줄
        final_report_list.append(["종합개선사항", "", data['종합의견']])
        # 5. 학교 간 빈 줄 추가 (선택사항)
        final_report_list.append(["", "", ""])

    report_df = pd.DataFrame(final_report_list)
    report_df.to_excel(workbook, index=False, header=False, sheet_name='점검결과보고서')
    workbook.close()

    st.download_button(
        label="📥 점검 결과 보고서(엑셀) 다운로드",
        data=output.getvalue(),
        file_name="교육과정_정밀점검_보고서.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
