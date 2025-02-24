import pandas as pd
import logging
import numpy as np

import matplotlib.pyplot as plt


# Machine Learning
from sklearn.model_selection import train_test_split

import xgboost as xgb

from helpers import get_raw_frequency_data, perform_fft_analysis, get_national_grid_data


# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")



def main():
    rows = []
    for date in pd.date_range("2023-07-01", "2024-12-01", freq="1MS"):
        df = get_raw_frequency_data(date.year, date.month)
        if df is None or df.empty:
            continue
        
        for i in range(0, len(df), 1800):
            try:
                timestamp = df.iloc[i]["dtm"]
                block = df.iloc[i:i+1800]
                fft_dict = perform_fft_analysis(block)
                fft_dict["timestamp"] = timestamp
                rows.append(fft_dict)
            except Exception as e:
                logging.error(f"Error processing block at index {i}: {e}")
    
    fft_df = pd.DataFrame(rows)
    fft_df['timestamp'] = pd.to_datetime(fft_df['timestamp'])
    fft_df.set_index('timestamp', inplace=True)

    fft_columns = fft_df.columns
        


    rolling_max_df = pd.DataFrame({
        f'{col}_{window}_max': fft_df[col].rolling(window).max()
        for col in fft_columns
        for window in ['1h', '3h', '6h']
    })

    rolling_min_df = pd.DataFrame({
        f'{col}_{window}_min': fft_df[col].rolling(window).min()
        for col in fft_columns
        for window in ['1h', '3h', '6h']
    })

    # # sine day of year
    # result_df['sin_day'] = np.sin(2 * np.pi * result_df.index.dayofyear / 365)
    # result_df['cos_day'] = np.cos(2 * np.pi * result_df.index.dayofyear / 365)

    # second of day
    fft_df['sin_second'] = np.sin(2 * np.pi * fft_df.index.second / 86400)
    fft_df['cos_second'] = np.cos(2 * np.pi * fft_df.index.second / 86400)




    # Drop original columns and combine with new features
    # result_df = result_df.drop(columns=fft_columns)
    fft_df = pd.concat([fft_df, rolling_min_df, rolling_max_df], axis=1)

    
    fuel_data = get_national_grid_data()
    if fuel_data is None:
        logging.error("Failed to load fuel data. Exiting.")
        return
    
    fuel_data['DATETIME'] = pd.to_datetime(fuel_data['DATETIME'])
    fuel_data.set_index('DATETIME', inplace=True)
    fuel_data = fuel_data[['CARBON_INTENSITY']]
    
    fft_df['CARBON_INTENSITY'] = fuel_data['CARBON_INTENSITY']
    fft_df.dropna(inplace=True)
    fft_df.drop_duplicates(inplace=True)



    validation_df = fft_df[fft_df.index > "2024-12-01"]
    fft_df = fft_df[fft_df.index <= "2024-12-01"]

    X = fft_df.drop(columns=['CARBON_INTENSITY'])
    y = fft_df['CARBON_INTENSITY']
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    xgb_model = xgb.XGBRegressor(
        # use gpu
        device = "cuda",
    )

    xgb_model.fit(X_train, y_train) 

    y_pred_val_xgb = xgb_model.predict(validation_df.drop(columns=['CARBON_INTENSITY']))
    # make a series

    fig = plt.figure(figsize=(20, 6))
    ax1 = fig.add_subplot(211)
    ax2 = fig.add_subplot(212)
    ax1.plot(validation_df.index, validation_df['CARBON_INTENSITY'], label="True Values", color='black')
    ax1.plot(validation_df.index, y_pred_val_xgb, label="XGBoost Predictions", alpha=0.5, color='red')
    
    ax1.set_xlabel("Timestamp")
    ax1.set_ylabel("Carbon Intensity")

    # remove the long movign average

    ax2.plot(validation_df.index, validation_df['CARBON_INTENSITY'] - validation_df['CARBON_INTENSITY'].rolling('12h').mean(), label="True Values", color='black')
    # turn into series
    y_pred_val_xgb = pd.Series(y_pred_val_xgb, index=validation_df.index)
    corrected = y_pred_val_xgb - y_pred_val_xgb.rolling('12h').mean()
    smoothed = corrected.rolling('1h').mean()
    ax2.plot(validation_df.index, smoothed, label="XGBoost Predictions", alpha=0.5, color='red')

    # smooth the data
    

    ax2.set_xlabel("Timestamp")
    ax2.set_ylabel("Carbon Intensity")
    ax2.set_title("Carbon Intensity - 12h Moving Average")
    plt.tight_layout()
    plt.savefig("validation.png")

    # scatter
    y_pred_test_xgb = xgb_model.predict(X_test)
    fig, ax = plt.subplots(figsize=(6, 6))

    # Create scatter plot
    ax.scatter(y_test, y_pred_test_xgb, color="#16BAC5", alpha=0.5, zorder=2)
    # plot a 1:1
    ax.plot([0, 300], [0, 300], color='gray', linestyle='--', zorder=3)
    

    # Configure axes
    ax.set_xlabel("Actual GB Carbon Intensity (gCO2/kWh)")
    ax.set_ylabel("Predicted GB Carbon Intensity (gCO2/kWh)")

    # Remove top and right spines
    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)

    # Add grid
    ax.yaxis.grid(color='gray', linestyle='dashed', zorder=0)
    ax.xaxis.grid(color='gray', linestyle='dashed', zorder=0)

    # Set title above the figure
    fig.suptitle("Grid frequency data can be used to predict carbon intensity",
                x=0.02,
                horizontalalignment='left',
                verticalalignment='bottom',
                fontsize=12,
                fontweight='bold',
                transform=fig.transFigure)

    # Adjust layout and save
    plt.tight_layout()
    plt.savefig("scatter_xgb.png", dpi=300, bbox_inches='tight')



    

if __name__ == "__main__":
    main()
