# frontend/Dockerfile
# Use an official Node runtime as a parent image
FROM node:18-alpine as base

# Set the working directory
WORKDIR /app

# Copy package.json and package-lock.json (or yarn.lock)
COPY package*.json ./

# Install dependencies using npm
RUN npm install

# Copy the rest of the application code
COPY . .

# Expose the port the app runs on (Vite default is 5173)
EXPOSE 5173

# Command to run the Vite development server
# Use --host to ensure it's accessible from outside the container
CMD ["npm", "run", "dev", "--", "--host"]