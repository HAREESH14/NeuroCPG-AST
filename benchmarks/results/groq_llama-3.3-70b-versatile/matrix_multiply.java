public class MatrixMultiplication {
    private static final int N = 3;

    public static void multiply(int[][] a, int[][] b, int[][] result) {
        for (int i = 0; i < N; i++) {
            for (int j = 0; j < N; j++) {
                result[i][j] = 0;
                for (int k = 0; k < N; k++) {
                    result[i][j] += a[i][k] * b[k][j];
                }
            }
        }
    }

    public static void printMatrix(int[][] matrix) {
        for (int i = 0; i < N; i++) {
            for (int j = 0; j < N; j++) {
                System.out.print(matrix[i][j] + " ");
            }
            System.out.println();
        }
    }

    public static void main(String[] args) {
        int[][] a = {{1, 2, 3}, {4, 5, 6}, {7, 8, 9}};
        int[][] b = {{9, 8, 7}, {6, 5, 4}, {3, 2, 1}};
        int[][] result = new int[N][N];

        multiply(a, b, result);
        System.out.println("Result:");
        printMatrix(result);
    }
}