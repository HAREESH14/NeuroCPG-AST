import java.util.Scanner;

public class MatrixMultiply {
    public static void multiply_2x2(int[][] A, int[][] B, int[][] C) {
        for (int i = 0; i < 2; ++i)
            for (int j = 0; j < 2; ++j) {
                C[i][j] = 0;
                for (int k = 0; k < 2; ++k)
                    C[i][j] += A[i][k] * B[k][j];
            }
    }

    public static void print_mat(int[][] M) {
        for (int i = 0; i < 2; ++i) {
            for (int j = 0; j < 2; ++j) System.out.print(M[i][j] + " ");
            System.out.println();
        }
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int[][] A = new int[2][2];
        int[][] B = new int[2][2];
        int[][] C = new int[2][2];
        for (int i = 0; i < 2; ++i) {
            for (int j = 0; j < 2; ++j) {
                A[i][j] = scanner.nextInt();
            }
        }
        for (int i = 0; i < 2; ++i) {
            for (int j = 0; j < 2; ++j) {
                B[i][j] = scanner.nextInt();
            }
        }
        System.out.println("Matrix A:");
        print_mat(A);
        System.out.println("Matrix B:");
        print_mat(B);
        multiply_2x2(A, B, C);
        System.out.println("A x B =");
        print_mat(C);
    }
}