import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import io
import time

# --- 1. 앱 설정 및 세션 상태 초기화 (가장 먼저 실행되어야 함) ---
st.set_page_config(page_title="고등학교 교육과정 정밀 점검 시스템", layout="wide")

# 세션 상태 초기화 로직 (오류 방지)
if 'analysis_data' not in st.session_state:
    st.session_state.analysis_data = []
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

def reset_all():
    st.session_state.analysis_data = []
    st.session_state.uploader_key += 1
    st.rerun()

# --- 2. 점검 지침 정의 (계산 로직 강화 버전) ---

CALCULATION_LOGIC = """
[학점 계산 및 검증 핵심 지침]
1. 학기별 총합 계산: (학교 지정 과목 학점) + (선택 과목 배정 학점) + (창의적 체험활동 학점)을 모두 더해야 함.
2. 선택 과목 처리: '12(택3)' 또는 '4(택1)'와 같은 형식에서 괄호 앞의 숫자(12 또는 4)가 그 학기에 학생이 이수하는 총 학점이므로 이 숫자를 합산에 사용함.
3. 창의적 체험활동(창체): 시트 하단에 있는 창체 학점(자율, 동아리, 봉사, 진로 등)을 반드시 찾아내어 매 학기 합계에 포함할 것 (보통 학기당 3학점).
4. 위계성 점검: 로마자(I, II)가 포함된 과목만 선이수 관계를 확인 (예: 물리학I -> 물리학II). '공통수학1, 2'나 '한국사1, 2'는 제외.
"""

GENERAL_RULES = f"""
{CALCULATION_LOGIC}
[일반 지침]
1.총이수학점(192이상), 2.필수이수학점(84이상), 3.학기단위완결성(학기별 32학점 권장), 
4.공통과목우선편성, 5.과목위계성, 6.학기간학점균형(격차5이내), 7.초과이수적정성, 
8.과목별학점범위준수, 9.교과군별필수충족, 10.2022개정과목사용, 11.국수영총합(81이내), 
12.한국사(각3학점), 13.체육(10학점이상/매학기), 14.종교과목선택권, 15.동일과목동일학점, 
16.과목명확성, 17.기록형식준수
"""

SCIENCE_CORE_RULES = """
[과학중점학교 추가 지침]
18.1학년과정: 과학/탐구실험 10학점 편성
19.과학선택과목: 물/화/생/지 I, II 전과목 개설
20.수학선택과목: 미적분II, 기하 등 심화과목 편성
21.정보교과: 정보 및 AI 관련 과목 필수 편성
22.융합과목: 과학/수학 융합 선택 과목 편성
"""

# --- 3. 모델 설정 함수 ---

def get_model(api_key, school_type):
    genai.configure(api_key=api_key)
    rules = GENERAL_RULES
    if school_type == "과학중점학교":
        rules += "\n" + SCIENCE_CORE_RULES
    
    instruction = f"""
    당신은 대한민국 고등학교 교육과정 전문가입니다. 
    제공된 엑셀 데이터를 분석하여 점검 리포트를 JSON 형식으로 작성하세요.
    특히 학기별 이수 학점 계산 시 '학교 지정', '선택 과목 학점', '창의적 체험활동'을 모두 합산해야 함을 명심하세요.
    
    [응답 규칙]
    - '상세근거'에 계산식 포함 (예: 지정(22)+선택(7)+창체(3)=32)
    - JSON 형식: {{"학교명": "", "점검리포트": [{{"항목": "", "판정": "", "상세근거": ""}}], "종합의견": ""}}
    """
    
    # 모델 선택 (안정적인 버전 우선)
    return genai.GenerativeModel(model_name='gemini-1.5-flash', system_instruction=instruction)

# --- 4. 분석 실행 함수 ---

def analyze_excel(model, file):
    try:
        all_sheets = pd.read_excel(file, sheet_name=None)
        content = ""
        for name, df in all_sheets.items():
            df_cleaned = df.fillna("")
            content += f"\n[시트: {name}]\n{df_cleaned.to_csv(index=False)}\n"
        
        response = model.generate_content(f"파일명: {file.name}\n데이터:\n{content}")
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_text)
    except Exception as e:
        return {"오류": str(e)}

# --- 5. UI 구성 ---

with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Gemini API Key", type="password")
    school_type = st.selectbox("학교 유형 선택", ["일반 고등학교", "과학중점학교"])
    st.divider()
    if st.button("🔄 전체 초기화"): reset_all()

st.title("🏫 고등학교 교육과정 정밀 점검 시스템")

# uploader_key를 안전하게 사용
u_key = f"uploader_{st.session_state.get('uploader_key', 0)}"
uploaded_files = st.file_uploader("엑셀 파일(.xlsx) 업로드", type=['xlsx'], accept_multiple_files=True, key=u_key)

if api_key and uploaded_files:
    model = get_model(api_key, school_type)
    
    if st.button("🔍 점검 시작", type="primary", use_container_width=True):
        st.session_state.analysis_data = []
        progress_bar = st.progress(0)
        
        for idx, file in enumerate(uploaded_files):
            st.write(f"⏳ {file.name} 분석 중...")
            result = analyze_excel(model, file)
            if "학교명" in result:
                st.session_state.analysis_data.append(result)
            else:
                st.error(f"{file.name} 분석 실패: {result.get('오류')}")
            
            progress_bar.progress((idx + 1) / len(uploaded_files))
            time.sleep(1) # API 호출 간격 조절
        st.success("모든 학교 점검 완료!")

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
