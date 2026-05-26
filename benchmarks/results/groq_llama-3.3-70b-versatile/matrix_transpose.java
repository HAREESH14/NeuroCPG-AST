import java.util.Scanner;

public class MatrixTranspose {
    public static void transpose(int n, int[][] a, int[][] t) {
        for (int i = 0; i < n; i++) 
            for (int j = 0; j < n; j++) 
                t[j][i] = a[i][j];
    }

    public static void printMat(int n, int m, int[][] a) {
        for (int i = 0; i < n; i++) { 
            for (int j = 0; j < m; j++) 
                System.out.print(a[i][j] + " "); 
            System.out.println(); 
        }
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int[][] A = new int[3][3];
        int[][] T = new int[3][3];
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 3; j++) {
                A[i][j] = scanner.nextInt();
            }
        }
        System.out.println("A:");
        printMat(3, 3, A);
        transpose(3, A, T);
        System.out.println("Transpose:");
        printMat(3, 3, T);
    }
}