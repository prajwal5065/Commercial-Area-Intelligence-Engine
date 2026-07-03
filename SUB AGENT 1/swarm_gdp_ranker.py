from concurrent.futures import ThreadPoolExecutor

from sovereign_agent import process_country_batch


def run_swarm(country_chunks):

    all_results = []

    with ThreadPoolExecutor(
        max_workers=len(country_chunks)
    ) as executor:

        futures = [
            executor.submit(
                process_country_batch,
                chunk
            )
            for chunk in country_chunks
        ]

        for future in futures:
            all_results.extend(
                future.result()
            )

    return all_results