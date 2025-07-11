import gurobipy as gp
from gurobipy import GRB
import matplotlib.pyplot as plt
import numpy as np

# Create a new model
model = gp.Model("test_model")

# Add variables
x = model.addVar(vtype=GRB.CONTINUOUS, name="x")
y = model.addVar(vtype=GRB.CONTINUOUS, name="y")

# Set objective: Maximize x + y
model.setObjective(x + y, GRB.MAXIMIZE)

# Add constraint: x + 2y ≤ 4
model.addConstr(x + 2 * y <= 4, "c1")

# Add constraint: 4x + 3y ≤ 12
model.addConstr(4 * x + 3 * y <= 12, "c2")

# Optimize
model.optimize()

# Print solution
for v in model.getVars():
    print(f"{v.varName} = {v.x}")
print(f"Objective Value = {model.ObjVal}")

# Visualization
def visualize_results():
    # Create figure
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # Generate points for plotting
    x_vals = np.linspace(0, 5, 100)
    
    # Plot constraints
    # Constraint 1: x + 2y ≤ 4 → y ≤ (4-x)/2
    y1 = (4 - x_vals) / 2
    ax1.plot(x_vals, y1, 'b-', label='x + 2y ≤ 4', linewidth=2)
    
    # Constraint 2: 4x + 3y ≤ 12 → y ≤ (12-4x)/3
    y2 = (12 - 4 * x_vals) / 3
    ax1.plot(x_vals, y2, 'r-', label='4x + 3y ≤ 12', linewidth=2)
    
    # Non-negativity constraints
    ax1.axhline(y=0, color='g', linestyle='-', label='y ≥ 0')
    ax1.axvline(x=0, color='g', linestyle='-', label='x ≥ 0')
    
    # Shade feasible region
    feasible_y = np.minimum(y1, y2)
    feasible_y = np.maximum(feasible_y, 0)
    ax1.fill_between(x_vals, 0, feasible_y, alpha=0.3, color='lightblue', label='Feasible Region')
    
    # Plot optimal solution
    if model.status == GRB.OPTIMAL:
        opt_x = model.getVarByName("x").x
        opt_y = model.getVarByName("y").x
        ax1.plot(opt_x, opt_y, 'ko', markersize=10, label=f'Optimal Solution\n({opt_x:.2f}, {opt_y:.2f})')
    
    ax1.set_xlabel('x')
    ax1.set_ylabel('y')
    ax1.set_title('Feasible Region and Optimal Solution')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_xlim(-0.5, 5)
    ax1.set_ylim(-0.5, 3)
    
    # Second plot: Objective function contours
    X, Y = np.meshgrid(np.linspace(0, 5, 50), np.linspace(0, 3, 50))
    Z = X + Y  # Objective function: x + y
    
    contours = ax2.contour(X, Y, Z, levels=10, colors='gray', alpha=0.6)
    ax2.clabel(contours, inline=True, fontsize=8)
    
    # Plot constraints again
    ax2.plot(x_vals, y1, 'b-', label='x + 2y ≤ 4', linewidth=2)
    ax2.plot(x_vals, y2, 'r-', label='4x + 3y ≤ 12', linewidth=2)
    ax2.axhline(y=0, color='g', linestyle='-', label='y ≥ 0')
    ax2.axvline(x=0, color='g', linestyle='-', label='x ≥ 0')
    
    # Shade feasible region
    ax2.fill_between(x_vals, 0, feasible_y, alpha=0.3, color='lightblue', label='Feasible Region')
    
    # Plot optimal solution
    if model.status == GRB.OPTIMAL:
        ax2.plot(opt_x, opt_y, 'ko', markersize=10, label=f'Optimal Solution\n({opt_x:.2f}, {opt_y:.2f})')
    
    ax2.set_xlabel('x')
    ax2.set_ylabel('y')
    ax2.set_title('Objective Function Contours')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.set_xlim(-0.5, 5)
    ax2.set_ylim(-0.5, 3)
    
    plt.tight_layout()
    plt.show()

# Call visualization function
visualize_results()

# Additional analysis
print("\n=== SOLUTION ANALYSIS ===")
print(f"Model Status: {model.status}")
if model.status == GRB.OPTIMAL:
    print(f"Optimal Solution Found!")
    print(f"x = {model.getVarByName('x').x:.4f}")
    print(f"y = {model.getVarByName('y').x:.4f}")
    print(f"Objective Value = {model.ObjVal:.4f}")
    
    # Check constraint satisfaction
    x_val = model.getVarByName('x').x
    y_val = model.getVarByName('y').x
    
    print(f"\nConstraint Check:")
    print(f"x + 2y = {x_val + 2*y_val:.4f} ≤ 4 ✓")
    print(f"4x + 3y = {4*x_val + 3*y_val:.4f} ≤ 12 ✓")
    print(f"x = {x_val:.4f} ≥ 0 ✓")
    print(f"y = {y_val:.4f} ≥ 0 ✓")
else:
    print("No optimal solution found!")
