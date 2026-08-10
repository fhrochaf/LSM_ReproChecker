from pathlib import Path

import pandas as pd

from flow_reproassesslsm_st1.config import INPUTS_PATH, OUTPUT_DIR, PDF_DIR
from flow_reproassesslsm_st1.crews.reprochecker_crew.reprochecker_crew import ReproCheckerCrew
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
    df.columns = df.columns.str.strip()

    pdf_files = sorted(p.name for p in PDF_DIR.glob("*.pdf"))

    ## TEMP
    total = len(pdf_files)
    processed_count = 0
    ## TEMP

    # for pdf_file in pdf_files:
    #     eid = Path(pdf_file).stem

    #     mask = df["EID"].astype(str).str.strip() == eid
    #     if not mask.any():
    #         print(f"Skipping {pdf_file}: EID={eid} not found in {INPUTS_PATH}.")
    #         continue
    #     row = df.loc[mask].iloc[0]

    #     if str(row.get("Filter_Decision", "")).strip() != "INCLUDE":
    #         print(f"Skipping EID={eid}: Filter_Decision is not INCLUDE.")
    #         continue

    #     if str(row.get("Reproducibility_Assessment", "")).strip():
    #         print(f"Skipping EID={eid} because it has already been processed.")
    #         ## TEMP
    #         processed_count += 1
    #         ## TEMP
    #         continue

    #     doi = str(row["DOI"]).strip()

    #     print(f"--- Running ReproCheckFlow for EID={eid} ---")
    #     repro_check_flow = ReproCheckFlow()
    #     repro_check_flow.state.publication_id = eid
    #     repro_check_flow.state.pdf_file = pdf_file
    #     repro_check_flow.state.doi = doi
    #     repro_check_flow._crew = ReproCheckerCrew(pdf_file=pdf_file)

    #     try:
    #         decision = repro_check_flow.check_prefilled_availability()

    #         ## TEMP
    #         print("availability decision:", decision)
    #         ## TEMP

    #         if decision == "prefilled":
    #             repro_check_flow.run_repro_check_from_csv()
    #         else:
    #             repro_check_flow.run_repro_check()

    #         repro_check_flow.save_report()

    #         ## TEMP
    #         processed_count += 1
    #         print(f"Progress: {processed_count}/{total}")
    #         ## TEMP
    #     except Exception as e:
    #         print(f"Error processing EID={eid}: {e}")
    #         raise e
    
    #     break #######################

    pdf_file = "2-s2.0-85108538442.pdf" #MILL: Channel Attentionâ€“based Deep Multiple Instance Learning for Landslide Recognition
    eid = Path(pdf_file).stem

    mask = df["EID"].astype(str).str.strip() == eid
    if not mask.any():
        print(f"Skipping {pdf_file}: EID={eid} not found in {INPUTS_PATH}.")
        raise Exception("EID not found in CSV") ############
    row = df.loc[mask].iloc[0]

    if str(row.get("Filter_Decision", "")).strip() != "INCLUDE":
        print(f"Skipping EID={eid}: Filter_Decision is not INCLUDE.")
        raise Exception("Filter_Decision is not INCLUDE") ############

    if str(row.get("Reproducibility_Assessment", "")).strip():
        print(f"Skipping EID={eid} because it has already been processed.")
        ## TEMP
        processed_count += 1
        ## TEMP
        raise Exception("EID already processed") ############

    doi = str(row["DOI"]).strip()

    print(f"--- Running ReproCheckFlow for EID={eid} ---")
    repro_check_flow = ReproCheckFlow()
    repro_check_flow.state.publication_id = eid
    repro_check_flow.state.pdf_file = pdf_file
    repro_check_flow.state.doi = doi
    repro_check_flow._crew = ReproCheckerCrew(pdf_file=pdf_file)

    try:
        decision = repro_check_flow.check_prefilled_availability()

        ## TEMP
        print("availability decision:", decision)
        ## TEMP

        if decision == "prefilled":
            repro_check_flow.run_repro_check_from_csv()
        else:
            repro_check_flow.run_repro_check()

        repro_check_flow.save_report()

        ## TEMP
        processed_count += 1
        print(f"Progress: {processed_count}/{total}")
        ## TEMP
    except Exception as e:
        print(f"Error processing EID={eid}: {e}")
        raise e