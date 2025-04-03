from src.inputs import get_model_data
from src.outputs import print_solution, store_result
from src.plotting import plot_region
from src.optim import optmodel
import sys

def main():
    #sys.stdout = open('output/optisched.txt', 'w') # Send results to file
    data, params = get_model_data()
    seqs, tstarts, brks = optmodel(
        data, 
        params, 
        start_from_initial_solution=True, 
        save_solution=False,
        verbose=False
        )
    routes, dropped, miss_appt, info = store_result(data, params, seqs, tstarts, brks)
    print_solution(data, routes, dropped, miss_appt, info)
    plot_region(routes, dropped, data, mapfile=params["name"]+"_map.html")

if __name__ == "__main__":
    main()