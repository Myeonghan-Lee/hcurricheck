import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import io
import time

# --- [중요] 계산 로직 강화를 위한 시스템 프롬프트 수정 ---
CALCULATION_LOGIC = """
[학점 계산 필수 규칙]
1. 학기별 총 이수 학점 계산식:
   - 해당 학기 총 학점 = (학교 지정 과목 학점 합계) + (선택 과목 배정 학점 합계) + (창의적 체험활동 학점)
2. 선택 과목 학점 추출:
   - '학점(택O)' 또는 '학점/(택O)' 형식에서, 괄호 앞의 숫자(X)가 해당 학기 학생이 이수하게 되는 '배정 학점'임.
   - 예: '4(택1)' -> 4학점 합산 / '12(택3)' -> 12학점 합산. (괄호 안의 숫자는 무시)
3. 창의적 체험활동(창체) 합산:
   - 시트 하단에 별도로 기재된 '창의적 체험활동', '자율/동아리/봉사/진로' 등의 학점(보통 학기당 3학점 내외)을 반드시 찾아내어 각 학기 총점에 합산할 것.
4. 학기 단위 완결성 점검:
   - 1학년 1학기부터 3학년 2학기까지 각 학기별 총합이 32학점(총 192학점 기준)이 되는지 확인.
   - 학기 간 학점 편차가 5학점 이상 벌어지면 'X' 판정.
"""

GENERAL_RULES = f"""
[일반 지침]
1.총이수학점(192이상), 2.필수이수학점(84이상), 3.학기단위완결성(학기별 합계 계산 주의), 
4.공통과목우선편성, 5.과목위계성(로마자 Ⅰ, Ⅱ 과목 대상), 
6.학기간학점균형(격차5이내), 7.초과이수적정성, 8.과목별학점범위준수, 
9.교과군별필수충족, 10.2022개정과목사용, 11.국수영총합(81이내), 12.한국사(각3학점), 
13.체육(10학점이상/매학기), 14.종교과목선택권, 15.동일과목동일학점, 16.과목명확성, 
17.기록형식준수
{CALCULATION_LOGIC}
"""

SCIENCE_CORE_RULES = """
[과학중점학교 추가 지침]
18.1학년과정: 과학/탐구실험 10학점 편성
19.과학선택과목: 물/화/생/지 I, II 전과목 개설 및 선택권 보장
20.수학선택과목: 미적분II, 기하 등 심화과목 편성
21.정보교과: 정보 및 AI 관련 과목 필수 편성
22.융합과목: 과학/수학 융합 선택 과목 편성
"""

def get_model(api_key, school_type):
    genai.configure(api_key=api_key)
    rules = GENERAL_RULES
    if school_type == "과학중점학교":
        rules += "\n" + SCIENCE_CORE_RULES
    
    instruction = f"""
    당신은 대한민국 고등학교 교육과정 편성표 분석 전문가입니다. 
    제시된 엑셀 데이터는 '학교 지정' 영역과 '학생 선택' 영역, 그리고 '창의적 체험활동' 영역으로 나뉩니다.
    
    {rules}
    
    [응답 규칙]
    - JSON 형식으로만 응답하세요.
    - '상세근거' 작성 시, 계산된 학기별 합계를 반드시 명시하세요. (예: 1-1학기: 지정(22)+선택(7)+창체(3)=32학점)
    - JSON: {{"학교명": "", "점검리포트": [{{"항목": "", "판정": "", "상세근거": ""}}], "종합의견": ""}}
    """
    
    available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    target = next((t for t in ['models/gemini-1.5-flash', 'gemini-1.5-flash'] if t in available), available[0])
    return genai.GenerativeModel(model_name=target, system_instruction=instruction)

# --- 4. 분석 실행 함수 (데이터 전처리 강화) ---

def analyze_excel(model, file):
    try:
        # 모든 시트를 읽어서 텍스트화
        all_sheets = pd.read_excel(file, sheet_name=None)
        content = ""
        for name, df in all_sheets.items():
            # 결측치를 0이나 빈 문자열로 처리하여 AI가 혼동하지 않게 함
            df_cleaned = df.fillna("")
            content += f"\n### 시트명: {name} ###\n{df_cleaned.to_csv(index=False)}\n"
        
        # AI에게 데이터 전달
        prompt = f"""
        파일명: {file.name}
        아래 데이터에서 학기별 학점을 계산하여 점검 리포트를 작성하세요.
        선택 과목의 'X(택Y)' 형식에서 X를 해당 학점 합계에 포함하는 것을 잊지 마세요.
        시트 하단의 '창의적 체험활동' 학점을 반드시 찾아내어 합산하세요.
        
        데이터:
        {content}
        """
        
        response = model.generate_content(prompt)
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
