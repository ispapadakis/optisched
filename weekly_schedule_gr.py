from src.inputs import get_model_data
from src.outputs import print_solution, store_result
from src.plotting import plot_region
from src.optim import optmodel

def main():
    data, params = get_model_data("region_gr")

    ### To begin new model
    # Set start_from_initial_solution=False
    # Set save_solution=True

    seqs, tstarts, brks = optmodel(
        **data,
        **params, 
        start_from_initial_solution=True, 
        save_solution=False,
        verbose=False
        )
    routes, info = store_result(data, params, seqs, tstarts, brks)
    print_solution(routes, info)
    plot_region(routes, data, mapfile=params["name"]+"_map.html")

if __name__ == "__main__":
    main()