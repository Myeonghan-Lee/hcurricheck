import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import io
import time

# --- 1. 앱 설정 ---
st.set_page_config(page_title="고등학교 교육과정 엑셀 점검 시스템", layout="wide")
st.title("📊 2027학년도 교육과정 자율 점검 (엑셀 분석형)")
st.info("404 모델 에러를 방지하기 위해 사용 가능한 최신 모델을 자동으로 탐색하여 연결합니다.")

# --- 2. 점검 지침 전문 (System Instruction) ---
SYSTEM_INSTRUCTION = """
당신은 대한민국 고등학교 교육과정 전문가입니다. 제공된 엑셀 데이터를 바탕으로 '자율 점검표'의 17가지 항목을 정밀 점검하세요.

[점검 항목]
1. 총 이수 학점 (192 이상)
2. 필수 이수 학점 (84 이상)
3. 학기 단위 이수 완결성
4. 공통 과목 우선 편성
5. 위계성 준수 (Ⅰ->Ⅱ)
6. 학기당 학점 균형 (격차 5 이내)
7. 초과 이수 적정화
8. 과목별 학점 범위 (공통 3~4, 한국사 3, 과탐실 1, 선택 3~5, 예체능/교양 2~4, 스포츠/생애 1~2)
9. 교과군별 필수 이수 학점 충족
10. 2022 개정 교육과정 과목 사용 (명칭 확인)
11. 국·수·영 총합 제한 (81 초과 금지)
12. 한국사 1, 2 편성 (각 3학점)
13. 체육 편성 (10학점 이상 및 매학기)
14. 종교 과목 선택권 (대체과목 편성)
15. 동일 과목 동일 학점 여부
16. 과목명 정확성 (띄어쓰기, 오탈자)
17. 기록 형식 준수 (<4(2)> 등)

반드시 아래 JSON 형식으로만 응답하세요.
{
    "학교명": "학교이름",
    "점검결과": { "항목1": "O/X (근거)", ... },
    "개선사항": "종합 의견"
}
"""

# --- 3. 모델 초기화 함수 (404 에러 해결 핵심) ---

def init_model_safely(api_key):
    try:
        genai.configure(api_key=api_key)
        
        # 사용 가능한 모델 목록 확인
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # 선호 모델 리스트 (가장 안정적인 경로 사용)
        preference = [
            'models/gemini-1.5-flash', 
            'models/gemini-1.5-flash-latest', 
            'models/gemini-1.5-pro'
        ]
        
        selected_model = None
        for target in preference:
            if target in available_models:
                selected_model = target
                break
        
        if not selected_model:
            selected_model = available_models[0] # 가용한 첫 번째 모델 선택
            
        return genai.GenerativeModel(
            model_name=selected_model,
            system_instruction=SYSTEM_INSTRUCTION
        )
    except Exception as e:
        st.error(f"모델 초기화 실패: {e}")
        return None

# --- 4. 엑셀 데이터 추출 함수 ---

def get_excel_content(uploaded_file):
    try:
        all_sheets = pd.read_excel(uploaded_file, sheet_name=None)
        combined_text = ""
        for name, df in all_sheets.items():
            combined_text += f"\n--- 시트: {name} ---\n"
            combined_text += df.to_csv(index=False)
        return combined_text
    except Exception as e:
        return f"엑셀 읽기 에러: {e}"

# --- 5. 분석 로직 ---

def run_analysis(model, excel_text, filename):
    retry_limit = 3
    for i in range(retry_limit):
        try:
            response = model.generate_content(f"파일명: {filename}\n데이터:\n{excel_text}")
            
            res_text = response.text
            if "```json" in res_text:
                res_text = res_text.split("```json")[1].split("```")[0]
            elif "```" in res_text:
                res_text = res_text.split("```")[1].split("```")[0]
            
            data = json.loads(res_text.strip())
            
            flat = {"파일명": filename, "학교명": data.get("학교명", "미확인")}
            flat.update(data.get("점검결과", {}))
            flat["개선사항"] = data.get("개선사항", "")
            return flat

        except Exception as e:
            if "429" in str(e):
                st.warning(f"할당량 초과... {i+1}차 재시도 (25초 대기)")
                time.sleep(25)
            else:
                return {"파일명": filename, "오류": str(e)}
    return {"파일명": filename, "오류": "재시도 횟수 초과"}

# --- 6. UI ---

api_key = st.sidebar.text_input("🔑 Gemini API Key 입력", type="password")

if api_key:
    model = init_model_safely(api_key)
    
    if model:
        st.sidebar.success(f"사용 모델: {model.model_name}")
        
        files = st.file_uploader("📁 점검할 엑셀 파일(.xlsx) 업로드", type=['xlsx'], accept_multiple_files=True)

        if files:
            if st.button(f"🚀 {len(files)}개 파일 분석 시작"):
                results = []
                progress = st.progress(0)
                
                for idx, file in enumerate(files):
                    st.write(f"분석 중: {file.name}...")
                    content = get_excel_content(file)
                    res = run_analysis(model, content, file.name)
                    results.append(res)
                    
                    progress.progress((idx + 1) / len(files))
                    if idx < len(files) - 1:
                        time.sleep(15) # RPM 안전거리 확보

                if results:
                    st.divider()
                    df = pd.DataFrame(results)
                    st.subheader("📊 전수 점검 결과 리포트")
                    st.dataframe(df, use_container_width=True)

                    # 다운로드 기능
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False)
                    st.download_button("📥 결과 엑셀 다운로드", output.getvalue(), "점검결과_종합.xlsx")
else:
    st.info("사이드바에 API Key를 입력해주세요.")
