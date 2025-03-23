from src.inputs import get_model_data
from src.plotting import plot_region
from src.optim import optmodel
import sys

def main():
    #sys.stdout = open('output/optisched.txt', 'w')
    data, params = get_model_data()
    routes, dropped = optmodel(data, params)
    plot_region(routes, dropped, data, mapfile=params["name"]+"_map.html")

if __name__ == "__main__":
    main()