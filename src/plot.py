import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("triple_pendulum.csv")
plt.plot(df.x1, df.y1, label="Bob 1")
plt.plot(df.x2, df.y2, label="Bob 2")
plt.plot(df.x3, df.y3, label="Bob 3")
plt.gca().set_aspect("equal")
plt.legend()
plt.show()


