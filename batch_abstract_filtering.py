import pandas as pd

from flow_reproassesslsm_st1.config import INPUTS_PATH, OUTPUT_DIR, PDF_DIR
from flow_reproassesslsm_st1.main import ReproCheckFlow

if __name__ == "__main__":
    print(f"INPUTS_PATH = {INPUTS_PATH.resolve()}")
    print(f"PDF_DIR     = {PDF_DIR.resolve()}")
    print(f"OUTPUT_DIR  = {OUTPUT_DIR.resolve()}")

    try:
        df = pd.read_csv(INPUTS_PATH, sep=';')
    except Exception as e:
        print(f"Error reading CSV: {e}")
        raise

    ## TEMP
    df_len = len(df)
    decided_count = 0
    ## TEMP

    for _, row in df.iterrows():
        if row["Filter_Decision"] in ["INCLUDE", "EXCLUDE"]:
            print(f"Skipping EID={row['EID']} because it has already been processed.")
            ## TEMP
            decided_count += 1
            ## TEMP
            continue
        eid = str(row["EID"]).strip()
        doi = str(row["DOI"]).strip()
        abstract = str(row["Abstract"]).strip()

        inputs = {
            "publication_id": eid,
            "pdf_file": f"{eid}.pdf",
            "doi": doi,
            "abstract": abstract,
        }

        print(f"--- Running ReproCheckFlow for EID={eid} ---")
        repro_check_flow = ReproCheckFlow()
        try:
            repro_check_flow.load_inputs(crewai_trigger_payload=inputs)
            
            ## TEMP
            print("Initial State: ", repro_check_flow.state)
            ## TEMP

            decision = repro_check_flow.filter_paper()

            ## TEMP
            print("decision:", decision)
            print("reason:", repro_check_flow.state.filter_reason)
            decided_count += 1
            print(f"Progress: {decided_count}/{df_len}")
            ## TEMP
        except Exception as e:
            print(f"Error processing EID={eid}: {e}")
            raise e